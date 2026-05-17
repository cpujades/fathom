"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import type { User } from "@supabase/supabase-js";
import { createApiClient } from "@fathom/api-client";

import { getSupabaseClient } from "../lib/supabaseClient";
import { buildSignInPath, getCurrentAppPath } from "../lib/url";

type AppShellContextValue = {
  accessToken: string | null;
  authenticated: boolean;
  loading: boolean;
  remainingSeconds: number | null;
  refreshUsage: () => Promise<void>;
  setRemainingSeconds: (value: number | null) => void;
  signOut: () => Promise<void>;
  user: User | null;
};

const AppShellContext = createContext<AppShellContextValue | null>(null);

const PREFETCH_ROUTES = ["/app", "/app/briefings", "/app/billing", "/app/account", "/app/briefings/new"];
const USAGE_CACHE_TTL_MS = 30_000;
const USAGE_BROADCAST_CHANNEL = "talven:usage";
const USAGE_STORAGE_KEY = "talven:usage-snapshot";
const DEFAULT_APP_PATH = "/app";

type UsageSnapshot = {
  fetchedAt: number;
  remainingSeconds: number | null;
};

let usageCache: UsageSnapshot | null = null;

type UsageRefreshResult = "ok" | "unauthorized" | "error";

function publishUsageSnapshot(snapshot: UsageSnapshot) {
  if (typeof window === "undefined" || snapshot.remainingSeconds === null) {
    return;
  }

  try {
    const channel = new BroadcastChannel(USAGE_BROADCAST_CHANNEL);
    channel.postMessage(snapshot);
    channel.close();
  } catch {
    // BroadcastChannel is a progressive enhancement; storage events cover older browsers.
  }

  try {
    window.localStorage.setItem(USAGE_STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    // Ignore private browsing or storage quota failures.
  }
}

function parseUsageSnapshot(value: unknown): UsageSnapshot | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  const snapshot = value as Partial<UsageSnapshot>;
  if (typeof snapshot.fetchedAt !== "number") {
    return null;
  }
  if (typeof snapshot.remainingSeconds !== "number" && snapshot.remainingSeconds !== null) {
    return null;
  }

  return {
    fetchedAt: snapshot.fetchedAt,
    remainingSeconds: snapshot.remainingSeconds ?? null
  };
}

export function AppShellProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const hydratedTokenRef = useRef<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [remainingSeconds, setRemainingSecondsState] = useState<number | null>(usageCache?.remainingSeconds ?? null);

  const setRemainingSeconds = useCallback((value: number | null) => {
    const snapshot = {
      fetchedAt: Date.now(),
      remainingSeconds: value
    };
    usageCache = snapshot;
    setRemainingSecondsState(value);
    publishUsageSnapshot(snapshot);
  }, []);

  const redirectToSignIn = useCallback(() => {
    router.replace(buildSignInPath(getCurrentAppPath(DEFAULT_APP_PATH)));
  }, [router]);

  const refreshUsageForToken = useCallback(
    async (token: string): Promise<UsageRefreshResult> => {
      try {
        const api = createApiClient(token);
        const { data, error, response } = await api.GET("/billing/usage");

        if (error) {
          if (response?.status === 401 || response?.status === 403) {
            return "unauthorized";
          }
          return "error";
        }

        setRemainingSeconds(data?.total_remaining_seconds ?? null);
        return "ok";
      } catch {
        return "error";
      }
    },
    [setRemainingSeconds]
  );

  const refreshUsage = useCallback(async () => {
    const token = hydratedTokenRef.current ?? accessToken;
    if (!token) {
      return;
    }

    const refreshResult = await refreshUsageForToken(token);
    if (refreshResult === "unauthorized") {
      hydratedTokenRef.current = null;
      setAuthenticated(false);
      setUser(null);
      setAccessToken(null);
      setRemainingSecondsState(null);
      redirectToSignIn();
    } else if (refreshResult === "error") {
      setRemainingSeconds(null);
    }
  }, [accessToken, redirectToSignIn, refreshUsageForToken, setRemainingSeconds]);

  useEffect(() => {
    for (const route of PREFETCH_ROUTES) {
      router.prefetch(route);
    }
  }, [router]);

  useEffect(() => {
    const applyUsageSnapshot = (snapshot: UsageSnapshot | null) => {
      if (!snapshot) {
        return;
      }
      if (usageCache && snapshot.fetchedAt < usageCache.fetchedAt) {
        return;
      }

      usageCache = snapshot;
      setRemainingSecondsState(snapshot.remainingSeconds);
    };

    let channel: BroadcastChannel | null = null;
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== USAGE_STORAGE_KEY || !event.newValue) {
        return;
      }

      try {
        applyUsageSnapshot(parseUsageSnapshot(JSON.parse(event.newValue)));
      } catch {
        // Ignore malformed cross-tab storage payloads.
      }
    };

    if (typeof window !== "undefined") {
      try {
        channel = new BroadcastChannel(USAGE_BROADCAST_CHANNEL);
        channel.onmessage = (event: MessageEvent<unknown>) => {
          applyUsageSnapshot(parseUsageSnapshot(event.data));
        };
      } catch {
        channel = null;
      }

      window.addEventListener("storage", handleStorage);
    }

    return () => {
      channel?.close();
      window.removeEventListener("storage", handleStorage);
    };
  }, []);

  useEffect(() => {
    let active = true;
    const supabase = getSupabaseClient();

    const syncFromSession = async () => {
      try {
        const { data: sessionData } = await supabase.auth.getSession();
        const session = sessionData.session;

        if (!active) {
          return;
        }

        if (!session) {
          setAuthenticated(false);
          setUser(null);
          setAccessToken(null);
          setRemainingSecondsState(null);
          setLoading(false);
          redirectToSignIn();
          return;
        }

        setAuthenticated(true);
        setUser(session.user);
        setAccessToken(session.access_token);
        hydratedTokenRef.current = session.access_token;

        const cacheIsFresh = usageCache && Date.now() - usageCache.fetchedAt < USAGE_CACHE_TTL_MS;
        if (cacheIsFresh) {
          setRemainingSecondsState(usageCache?.remainingSeconds ?? null);
          setLoading(false);
        } else {
          const refreshResult = await refreshUsageForToken(session.access_token);
          if (refreshResult === "unauthorized") {
            setAuthenticated(false);
            setUser(null);
            setAccessToken(null);
            setRemainingSecondsState(null);
            setLoading(false);
            redirectToSignIn();
            return;
          }
          if (refreshResult === "error") {
            setRemainingSeconds(null);
          }
          if (!active) {
            return;
          }
          setLoading(false);
        }
      } catch {
        if (!active) {
          return;
        }
        setAuthenticated(false);
        setUser(null);
        setAccessToken(null);
        setRemainingSecondsState(null);
        setLoading(false);
        redirectToSignIn();
      }
    };

    void syncFromSession();

    const { data: authListener } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (!active) {
        return;
      }

      if (event === "INITIAL_SESSION") {
        return;
      }

      if (!session) {
        hydratedTokenRef.current = null;
        setAuthenticated(false);
        setUser(null);
        setAccessToken(null);
        setRemainingSecondsState(null);
        redirectToSignIn();
        return;
      }

      setAuthenticated(true);
      setUser(session.user);
      setAccessToken(session.access_token);

      const tokenChanged = hydratedTokenRef.current !== session.access_token;
      const cacheIsFresh = usageCache && Date.now() - usageCache.fetchedAt < USAGE_CACHE_TTL_MS;
      if (tokenChanged || !cacheIsFresh) {
        const refreshResult = await refreshUsageForToken(session.access_token);
        if (refreshResult === "unauthorized") {
          hydratedTokenRef.current = null;
          setAuthenticated(false);
          setUser(null);
          setAccessToken(null);
          setRemainingSecondsState(null);
          redirectToSignIn();
          return;
        }
        if (refreshResult === "error") {
          setRemainingSeconds(null);
        }
      } else {
        setRemainingSecondsState(usageCache?.remainingSeconds ?? null);
      }
      hydratedTokenRef.current = session.access_token;
    });

    return () => {
      active = false;
      authListener.subscription.unsubscribe();
    };
  }, [redirectToSignIn, refreshUsageForToken, setRemainingSeconds]);

  const signOut = useCallback(async () => {
    const supabase = getSupabaseClient();
    await supabase.auth.signOut();
    usageCache = null;
    setAuthenticated(false);
    setUser(null);
    setAccessToken(null);
    setRemainingSecondsState(null);
    router.replace("/signin");
  }, [router]);

  const value = useMemo<AppShellContextValue>(
    () => ({
      accessToken,
      authenticated,
      loading,
      remainingSeconds,
      refreshUsage,
      setRemainingSeconds,
      signOut,
      user
    }),
    [accessToken, authenticated, loading, refreshUsage, remainingSeconds, setRemainingSeconds, signOut, user]
  );

  return <AppShellContext.Provider value={value}>{children}</AppShellContext.Provider>;
}

export function useAppShell(): AppShellContextValue {
  const context = useContext(AppShellContext);
  if (!context) {
    throw new Error("useAppShell must be used within AppShellProvider.");
  }
  return context;
}

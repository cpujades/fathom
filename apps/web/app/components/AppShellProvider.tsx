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
  setRemainingSeconds: (value: number | null) => void;
  signOut: () => Promise<void>;
  user: User | null;
};

const AppShellContext = createContext<AppShellContextValue | null>(null);

const PREFETCH_ROUTES = ["/app", "/app/briefings", "/app/billing", "/app/account", "/app/briefings/new"];
const USAGE_CACHE_TTL_MS = 30_000;
const DEFAULT_APP_PATH = "/app";

let usageCache: {
  fetchedAt: number;
  remainingSeconds: number | null;
} | null = null;

export function AppShellProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const hydratedTokenRef = useRef<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [remainingSeconds, setRemainingSecondsState] = useState<number | null>(usageCache?.remainingSeconds ?? null);

  const setRemainingSeconds = useCallback((value: number | null) => {
    usageCache = {
      fetchedAt: Date.now(),
      remainingSeconds: value
    };
    setRemainingSecondsState(value);
  }, []);

  const redirectToSignIn = useCallback(() => {
    router.replace(buildSignInPath(getCurrentAppPath(DEFAULT_APP_PATH)));
  }, [router]);

  const refreshUsage = useCallback(
    async (token: string) => {
      const api = createApiClient(token);
      const { data } = await api.GET("/billing/usage");
      setRemainingSeconds(data?.total_remaining_seconds ?? null);
    },
    [setRemainingSeconds]
  );

  useEffect(() => {
    for (const route of PREFETCH_ROUTES) {
      router.prefetch(route);
    }
  }, [router]);

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
          await refreshUsage(session.access_token);
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
        await refreshUsage(session.access_token);
      } else {
        setRemainingSecondsState(usageCache?.remainingSeconds ?? null);
      }
      hydratedTokenRef.current = session.access_token;
    });

    return () => {
      active = false;
      authListener.subscription.unsubscribe();
    };
  }, [redirectToSignIn, refreshUsage]);

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
      setRemainingSeconds,
      signOut,
      user
    }),
    [accessToken, authenticated, loading, remainingSeconds, setRemainingSeconds, signOut, user]
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

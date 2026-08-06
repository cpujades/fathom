"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import type { Session, User } from "@supabase/supabase-js";
import { createApiClient } from "@fathom/api-client";

import {
  assertAuthenticatedRequestScopeCurrent,
  cacheUsageSnapshot,
  captureAuthenticatedRequestScope,
  getCachedUsageSnapshot,
  getUsageBroadcastChannelName,
  getUsageStorageKey,
  isAuthenticatedDataScopeChangedError,
  resetAuthenticatedAppDataCache,
  type UsageSnapshot
} from "../lib/appDataCache";
import { getSupabaseClient } from "../lib/supabaseClient";
import { buildSignInPath, getCurrentAppPath } from "../lib/url";
import { isUsageSnapshotStale } from "../lib/usage";

type AppShellContextValue = {
  accessToken: string | null;
  authenticated: boolean;
  debtSeconds: number | null;
  hasActivePaidSubscription: boolean | null;
  isBlocked: boolean | null;
  loading: boolean;
  remainingSeconds: number | null;
  refreshUsage: () => Promise<void>;
  usageRefreshFailed: boolean;
  setRemainingSeconds: (
    userId: string,
    value: number | null,
    hasActivePaidSubscription?: boolean | null,
    debtSeconds?: number | null,
    isBlocked?: boolean | null
  ) => void;
  signOut: () => Promise<void>;
  user: User | null;
};

type ActiveSessionIdentity = {
  accessToken: string;
  userId: string;
};

const AppShellContext = createContext<AppShellContextValue | null>(null);

const PREFETCH_ROUTES = ["/app", "/app/briefings", "/app/billing", "/app/account", "/app/briefings/new"];
const DEFAULT_APP_PATH = "/app";

type UsageRefreshResult = "ok" | "unauthorized" | "error" | "stale";

function publishUsageSnapshot(userId: string, snapshot: UsageSnapshot) {
  if (typeof window === "undefined" || snapshot.remainingSeconds === null) {
    return;
  }

  try {
    const channel = new BroadcastChannel(getUsageBroadcastChannelName(userId));
    channel.postMessage(snapshot);
    channel.close();
  } catch {
    // BroadcastChannel is a progressive enhancement; storage events cover older browsers.
  }

  try {
    window.localStorage.setItem(getUsageStorageKey(userId), JSON.stringify(snapshot));
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
    debtSeconds: typeof snapshot.debtSeconds === "number" ? snapshot.debtSeconds : null,
    fetchedAt: snapshot.fetchedAt,
    hasActivePaidSubscription:
      typeof snapshot.hasActivePaidSubscription === "boolean" ? snapshot.hasActivePaidSubscription : null,
    isBlocked: typeof snapshot.isBlocked === "boolean" ? snapshot.isBlocked : null,
    remainingSeconds: snapshot.remainingSeconds ?? null
  };
}

function readStoredUsageSnapshot(userId: string): UsageSnapshot | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const value = window.localStorage.getItem(getUsageStorageKey(userId));
    return value ? parseUsageSnapshot(JSON.parse(value)) : null;
  } catch {
    return null;
  }
}

export function AppShellProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const activeSessionRef = useRef<ActiveSessionIdentity | null>(null);
  const authTransitionRef = useRef(0);
  const [sessionGeneration, setSessionGeneration] = useState(0);
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  const [debtSeconds, setDebtSeconds] = useState<number | null>(null);
  const [hasActivePaidSubscription, setHasActivePaidSubscription] = useState<boolean | null>(null);
  const [isBlocked, setIsBlocked] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [remainingSeconds, setRemainingSecondsState] = useState<number | null>(null);
  const [usageRefreshFailed, setUsageRefreshFailed] = useState(false);

  const commitUsageSnapshot = useCallback((userId: string, snapshot: UsageSnapshot): boolean => {
    if (!cacheUsageSnapshot(userId, snapshot)) {
      return false;
    }
    setRemainingSecondsState(snapshot.remainingSeconds);
    setDebtSeconds(snapshot.debtSeconds);
    setHasActivePaidSubscription(snapshot.hasActivePaidSubscription);
    setIsBlocked(snapshot.isBlocked);
    setUsageRefreshFailed(false);
    publishUsageSnapshot(userId, snapshot);
    return true;
  }, []);

  const setRemainingSeconds = useCallback(
    (
      userId: string,
      value: number | null,
      paidSubscription?: boolean | null,
      nextDebtSeconds?: number | null,
      nextIsBlocked?: boolean | null
    ) => {
      const currentSnapshot = getCachedUsageSnapshot(userId);
      commitUsageSnapshot(userId, {
        debtSeconds:
          nextDebtSeconds === undefined ? currentSnapshot?.debtSeconds ?? null : nextDebtSeconds,
        fetchedAt: Date.now(),
        hasActivePaidSubscription:
          paidSubscription === undefined
            ? currentSnapshot?.hasActivePaidSubscription ?? null
            : paidSubscription,
        isBlocked: nextIsBlocked === undefined ? currentSnapshot?.isBlocked ?? null : nextIsBlocked,
        remainingSeconds: value
      });
    },
    [commitUsageSnapshot]
  );

  const applyAuthSession = useCallback((session: Session | null) => {
    const userId = session?.user.id ?? null;
    resetAuthenticatedAppDataCache(userId);
    activeSessionRef.current = session
      ? { accessToken: session.access_token, userId: session.user.id }
      : null;
    setAuthenticated(Boolean(session));
    setUser(session?.user ?? null);
    setAccessToken(session?.access_token ?? null);
    setDebtSeconds(null);
    setHasActivePaidSubscription(null);
    setIsBlocked(null);
    setRemainingSecondsState(null);
    setUsageRefreshFailed(false);
    setSessionGeneration((generation) => generation + 1);
  }, []);

  const redirectToSignIn = useCallback(() => {
    router.replace(buildSignInPath(getCurrentAppPath(DEFAULT_APP_PATH)));
  }, [router]);

  const refreshUsageForSession = useCallback(
    async (userId: string, token: string): Promise<UsageRefreshResult> => {
      try {
        const requestScope = captureAuthenticatedRequestScope(userId);
        const api = createApiClient(token);
        const { data, error, response } = await api.GET("/billing/usage");
        assertAuthenticatedRequestScopeCurrent(requestScope);

        if (error) {
          if (response?.status === 401 || response?.status === 403) {
            return "unauthorized";
          }
          return "error";
        }

        commitUsageSnapshot(userId, {
          debtSeconds: data?.debt_seconds ?? null,
          fetchedAt: Date.now(),
          hasActivePaidSubscription: data?.has_active_paid_subscription ?? null,
          isBlocked: data?.is_blocked ?? null,
          remainingSeconds: data?.total_remaining_seconds ?? null
        });
        return "ok";
      } catch (error) {
        return isAuthenticatedDataScopeChangedError(error) ? "stale" : "error";
      }
    },
    [commitUsageSnapshot]
  );

  const refreshUsage = useCallback(async () => {
    const identity = activeSessionRef.current;
    if (!identity) {
      return;
    }

    const refreshResult = await refreshUsageForSession(identity.userId, identity.accessToken);
    if (refreshResult === "unauthorized" && activeSessionRef.current?.userId === identity.userId) {
      authTransitionRef.current += 1;
      applyAuthSession(null);
      setLoading(false);
      redirectToSignIn();
    } else if (refreshResult === "error") {
      setUsageRefreshFailed(true);
    }
  }, [applyAuthSession, redirectToSignIn, refreshUsageForSession]);

  useEffect(() => {
    for (const route of PREFETCH_ROUTES) {
      router.prefetch(route);
    }
  }, [router]);

  useEffect(() => {
    const userId = user?.id;
    if (!userId) {
      return;
    }

    const applyUsageSnapshot = (snapshot: UsageSnapshot | null) => {
      if (!snapshot) {
        return;
      }
      const current = getCachedUsageSnapshot(userId);
      if (current && snapshot.fetchedAt < current.fetchedAt) {
        return;
      }
      if (cacheUsageSnapshot(userId, snapshot)) {
        setRemainingSecondsState(snapshot.remainingSeconds);
        setDebtSeconds(snapshot.debtSeconds);
        setHasActivePaidSubscription(snapshot.hasActivePaidSubscription);
        setIsBlocked(snapshot.isBlocked);
        setUsageRefreshFailed(false);
      }
    };

    let channel: BroadcastChannel | null = null;
    const storageKey = getUsageStorageKey(userId);
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== storageKey || !event.newValue) {
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
        channel = new BroadcastChannel(getUsageBroadcastChannelName(userId));
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
  }, [user?.id]);

  useEffect(() => {
    let active = true;
    const supabase = getSupabaseClient();

    const settleSession = async (session: Session | null, transitionId: number) => {
      if (!active || transitionId !== authTransitionRef.current) {
        return;
      }

      applyAuthSession(session);
      if (!session) {
        setLoading(false);
        redirectToSignIn();
        return;
      }

      const userId = session.user.id;
      const storedSnapshot = readStoredUsageSnapshot(userId);
      if (
        storedSnapshot &&
        storedSnapshot.debtSeconds !== null &&
        storedSnapshot.hasActivePaidSubscription !== null &&
        storedSnapshot.isBlocked !== null &&
        !isUsageSnapshotStale(storedSnapshot, Date.now())
      ) {
        commitUsageSnapshot(userId, storedSnapshot);
        setLoading(false);
        return;
      }

      const refreshResult = await refreshUsageForSession(userId, session.access_token);
      if (!active || transitionId !== authTransitionRef.current || refreshResult === "stale") {
        return;
      }
      if (refreshResult === "unauthorized") {
        authTransitionRef.current += 1;
        applyAuthSession(null);
        setLoading(false);
        redirectToSignIn();
        return;
      }
      if (refreshResult === "error") {
        setUsageRefreshFailed(true);
      }
      setLoading(false);
    };

    const syncFromSession = async () => {
      const transitionId = ++authTransitionRef.current;
      try {
        const { data: sessionData } = await supabase.auth.getSession();
        await settleSession(sessionData.session, transitionId);
      } catch {
        if (!active || transitionId !== authTransitionRef.current) {
          return;
        }
        applyAuthSession(null);
        setLoading(false);
        redirectToSignIn();
      }
    };

    void syncFromSession();

    const { data: authListener } = supabase.auth.onAuthStateChange((_event, session) => {
      const transitionId = ++authTransitionRef.current;
      void settleSession(session, transitionId);
    });

    return () => {
      active = false;
      authTransitionRef.current += 1;
      authListener.subscription.unsubscribe();
    };
  }, [applyAuthSession, commitUsageSnapshot, redirectToSignIn, refreshUsageForSession, setRemainingSeconds]);

  useEffect(() => {
    if (!accessToken || !user?.id) {
      return;
    }

    const refreshStaleUsage = () => {
      const snapshot = getCachedUsageSnapshot(user.id);
      if (isUsageSnapshotStale(snapshot, Date.now())) {
        void refreshUsage();
      }
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        refreshStaleUsage();
      }
    };

    window.addEventListener("focus", refreshStaleUsage);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.removeEventListener("focus", refreshStaleUsage);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [accessToken, refreshUsage, user?.id]);

  const signOut = useCallback(async () => {
    const transitionId = ++authTransitionRef.current;
    applyAuthSession(null);
    setLoading(false);
    router.replace("/signin");

    const supabase = getSupabaseClient();
    try {
      await supabase.auth.signOut();
    } finally {
      if (transitionId === authTransitionRef.current) {
        resetAuthenticatedAppDataCache(null);
      }
    }
  }, [applyAuthSession, router]);

  const value = useMemo<AppShellContextValue>(
    () => ({
      accessToken,
      authenticated,
      debtSeconds,
      hasActivePaidSubscription,
      isBlocked,
      loading,
      remainingSeconds,
      refreshUsage,
      setRemainingSeconds,
      signOut,
      usageRefreshFailed,
      user
    }),
    [
      accessToken,
      authenticated,
      debtSeconds,
      hasActivePaidSubscription,
      isBlocked,
      loading,
      refreshUsage,
      remainingSeconds,
      setRemainingSeconds,
      signOut,
      usageRefreshFailed,
      user
    ]
  );

  return (
    <AppShellContext.Provider key={sessionGeneration} value={value}>
      {children}
    </AppShellContext.Provider>
  );
}

export function useAppShell(): AppShellContextValue {
  const context = useContext(AppShellContext);
  if (!context) {
    throw new Error("useAppShell must be used within AppShellProvider.");
  }
  return context;
}

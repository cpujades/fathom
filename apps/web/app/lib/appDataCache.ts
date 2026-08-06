import type {
  BillingAccountResponse,
  BriefingSessionResponse,
  PlanResponse,
  UsageOverviewResponse
} from "@fathom/api-client";
import { createApiClient } from "@fathom/api-client";

import type { BriefingListResponse, BriefingsQueryOptions } from "./briefings";
import { DEFAULT_BRIEFINGS_QUERY } from "./briefings";
import {
  AuthenticatedDataScopeChangedError,
  AuthenticatedDataScopeController,
  type AuthenticatedRequestScope
} from "./authenticatedDataScope";

export { AuthenticatedDataScopeChangedError } from "./authenticatedDataScope";
export type { AuthenticatedRequestScope } from "./authenticatedDataScope";

export type BillingSnapshot = {
  accountData: BillingAccountResponse | null;
  plansData: PlanResponse[];
  usageData: UsageOverviewResponse | null;
};

export type UsageSnapshot = {
  debtSeconds: number | null;
  fetchedAt: number;
  hasActivePaidSubscription: boolean | null;
  isBlocked: boolean | null;
  remainingSeconds: number | null;
};

type ScopedValue<T> = {
  scope: AuthenticatedRequestScope;
  value: T;
};

type TimedValue<T> = {
  fetchedAt: number;
  value: T;
};

const CACHE_TTL_MS = 30_000;
const BRIEFINGS_CACHE_INVALIDATED_AT_KEY_PREFIX = "talven:briefings-cache-invalidated-at";
const USAGE_BROADCAST_CHANNEL_PREFIX = "talven:usage";
const USAGE_STORAGE_KEY_PREFIX = "talven:usage-snapshot";

const authScopeController = new AuthenticatedDataScopeController();

let briefingsCache: ScopedValue<TimedValue<BriefingListResponse>> | null = null;
let briefingsRequest: ScopedValue<Promise<BriefingListResponse>> | null = null;
let observedBriefingsInvalidatedAt = 0;

let billingCache: ScopedValue<TimedValue<BillingSnapshot>> | null = null;
let billingRequest: ScopedValue<Promise<BillingSnapshot>> | null = null;

let usageCache: ScopedValue<UsageSnapshot> | null = null;
let sessionCache = new Map<string, ScopedValue<TimedValue<BriefingSessionResponse>>>();
let sessionRequests = new Map<string, ScopedValue<Promise<BriefingSessionResponse | null>>>();

function clearInMemoryCaches(): void {
  briefingsCache = null;
  briefingsRequest = null;
  billingCache = null;
  billingRequest = null;
  usageCache = null;
  sessionCache = new Map();
  sessionRequests = new Map();
  observedBriefingsInvalidatedAt = 0;
}

function removeStoredUsageSnapshot(userId: string): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.removeItem(getUsageStorageKey(userId));
  } catch {
    // Auth cache reset must still succeed when storage is unavailable.
  }
}

/**
 * Establish a new authenticated cache generation and invalidate every value or
 * request created by the previous session. Raw access tokens never enter this
 * cache boundary.
 */
export function resetAuthenticatedAppDataCache(userId: string | null): void {
  const { nextUserId, previousUserId } = authScopeController.reset(userId);
  clearInMemoryCaches();

  if (previousUserId && previousUserId !== nextUserId) {
    removeStoredUsageSnapshot(previousUserId);
  }
}

export function captureAuthenticatedRequestScope(userId: string): AuthenticatedRequestScope {
  return authScopeController.capture(userId);
}

export function isAuthenticatedRequestScopeCurrent(scope: AuthenticatedRequestScope): boolean {
  return authScopeController.isCurrent(scope);
}

export function assertAuthenticatedRequestScopeCurrent(scope: AuthenticatedRequestScope): void {
  authScopeController.assertCurrent(scope);
}

export function isAuthenticatedDataScopeChangedError(error: unknown): boolean {
  return error instanceof AuthenticatedDataScopeChangedError;
}

function currentScope(userId: string): AuthenticatedRequestScope | null {
  try {
    return captureAuthenticatedRequestScope(userId);
  } catch {
    return null;
  }
}

function scopesMatch(left: AuthenticatedRequestScope, right: AuthenticatedRequestScope): boolean {
  return left.userId === right.userId && left.generation === right.generation;
}

function storageKey(prefix: string, userId: string): string {
  return `${prefix}:${encodeURIComponent(userId)}`;
}

export function getUsageBroadcastChannelName(userId: string): string {
  return storageKey(USAGE_BROADCAST_CHANNEL_PREFIX, userId);
}

export function getUsageStorageKey(userId: string): string {
  return storageKey(USAGE_STORAGE_KEY_PREFIX, userId);
}

export function getCachedUsageSnapshot(userId: string): UsageSnapshot | null {
  const scope = currentScope(userId);
  if (!scope || !usageCache || !scopesMatch(usageCache.scope, scope)) {
    return null;
  }
  return usageCache.value;
}

export function cacheUsageSnapshot(userId: string, snapshot: UsageSnapshot): boolean {
  const scope = currentScope(userId);
  if (!scope) {
    return false;
  }
  usageCache = { scope, value: snapshot };
  return true;
}

export function getCachedBriefings(userId: string): BriefingListResponse | null {
  const scope = currentScope(userId);
  if (!scope || !briefingsCache || !scopesMatch(briefingsCache.scope, scope)) {
    return null;
  }
  return briefingsCache.value.value;
}

export function invalidateBriefingsCache(userId: string): void {
  const scope = captureAuthenticatedRequestScope(userId);
  briefingsCache = null;
  if (typeof window !== "undefined") {
    const invalidatedAt = Date.now();
    observedBriefingsInvalidatedAt = invalidatedAt;
    try {
      window.localStorage.setItem(
        storageKey(BRIEFINGS_CACHE_INVALIDATED_AT_KEY_PREFIX, scope.userId),
        String(invalidatedAt)
      );
    } catch {
      // Cache invalidation is a performance hint; storage may be unavailable.
    }
  }
}

export function hasFreshBriefingsCache(userId: string): boolean {
  const scope = currentScope(userId);
  if (!scope || !briefingsCache || !scopesMatch(briefingsCache.scope, scope)) {
    return false;
  }
  if (hasBriefingsCacheBeenInvalidatedInAnotherTab(scope)) {
    briefingsCache = null;
    return false;
  }
  return Date.now() - briefingsCache.value.fetchedAt < CACHE_TTL_MS;
}

function hasBriefingsCacheBeenInvalidatedInAnotherTab(scope: AuthenticatedRequestScope): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  try {
    const invalidatedAt = Number(
      window.localStorage.getItem(storageKey(BRIEFINGS_CACHE_INVALIDATED_AT_KEY_PREFIX, scope.userId)) ?? "0"
    );
    if (!Number.isFinite(invalidatedAt) || invalidatedAt <= observedBriefingsInvalidatedAt) {
      return false;
    }

    observedBriefingsInvalidatedAt = invalidatedAt;
    return true;
  } catch {
    return false;
  }
}

function normalizeBriefingsQuery(
  options?: BriefingsQueryOptions
): Required<BriefingsQueryOptions> {
  const normalizedQuery = options?.query?.trim() ?? "";

  return {
    limit: options?.limit ?? DEFAULT_BRIEFINGS_QUERY.limit,
    offset: options?.offset ?? DEFAULT_BRIEFINGS_QUERY.offset,
    query: normalizedQuery,
    sort: options?.sort ?? DEFAULT_BRIEFINGS_QUERY.sort,
    sourceType: options?.sourceType ?? DEFAULT_BRIEFINGS_QUERY.sourceType
  };
}

function isDefaultBriefingsQuery(query: Required<BriefingsQueryOptions>): boolean {
  return (
    query.limit === DEFAULT_BRIEFINGS_QUERY.limit &&
    query.offset === DEFAULT_BRIEFINGS_QUERY.offset &&
    query.query === DEFAULT_BRIEFINGS_QUERY.query &&
    query.sort === DEFAULT_BRIEFINGS_QUERY.sort &&
    query.sourceType === DEFAULT_BRIEFINGS_QUERY.sourceType
  );
}

export async function loadBriefings(
  userId: string,
  accessToken: string,
  options?: BriefingsQueryOptions
): Promise<BriefingListResponse> {
  const scope = captureAuthenticatedRequestScope(userId);
  const query = normalizeBriefingsQuery(options);
  const cacheable = isDefaultBriefingsQuery(query);

  if (cacheable && briefingsRequest && scopesMatch(briefingsRequest.scope, scope)) {
    return briefingsRequest.value;
  }

  const request = (async () => {
    try {
      const api = createApiClient(accessToken);
      const { data, error } = await api.GET("/briefings", {
        params: {
          query: {
            limit: query.limit,
            offset: query.offset,
            query: query.query || undefined,
            sort: query.sort,
            sourceType: query.sourceType
          }
        }
      });
      assertAuthenticatedRequestScopeCurrent(scope);
      if (error) throw error;
      if (!data) throw new Error("The briefing library response was empty.");

      if (cacheable) {
        briefingsCache = {
          scope,
          value: {
            value: data,
            fetchedAt: Date.now()
          }
        };
      }

      return data;
    } catch (error) {
      assertAuthenticatedRequestScopeCurrent(scope);
      throw error;
    }
  })();

  const scopedRequest = { scope, value: request };
  if (cacheable) {
    briefingsRequest = scopedRequest;
  }

  try {
    return await request;
  } finally {
    if (cacheable && briefingsRequest === scopedRequest) {
      briefingsRequest = null;
    }
  }
}

export function getCachedBillingSnapshot(userId: string): BillingSnapshot | null {
  const scope = currentScope(userId);
  if (!scope || !billingCache || !scopesMatch(billingCache.scope, scope)) {
    return null;
  }
  return billingCache.value.value;
}

export function hasFreshBillingCache(userId: string): boolean {
  const scope = currentScope(userId);
  return Boolean(
    scope &&
      billingCache &&
      scopesMatch(billingCache.scope, scope) &&
      Date.now() - billingCache.value.fetchedAt < CACHE_TTL_MS
  );
}

export async function loadBillingSnapshot(
  userId: string,
  accessToken: string,
  options: { refreshAfterInFlight?: boolean } = {}
): Promise<BillingSnapshot> {
  const scope = captureAuthenticatedRequestScope(userId);
  if (billingRequest && scopesMatch(billingRequest.scope, scope)) {
    if (!options.refreshAfterInFlight) {
      return billingRequest.value;
    }

    const inFlightRequest = billingRequest;
    try {
      await inFlightRequest.value;
    } catch {
      // A terminal billing operation still warrants one authoritative refresh
      // even when the page's earlier snapshot request failed.
    }
    assertAuthenticatedRequestScopeCurrent(scope);
    if (billingRequest === inFlightRequest) {
      billingRequest = null;
    }
  }

  const api = createApiClient(accessToken);
  const request = (async () => {
    try {
      const [
        { data: plansData, error: plansError },
        { data: usageData, error: usageError },
        { data: accountData, error: accountError }
      ] = await Promise.all([api.GET("/billing/plans"), api.GET("/billing/usage"), api.GET("/billing/account")]);

      assertAuthenticatedRequestScopeCurrent(scope);
      if (plansError) {
        throw plansError;
      }
      if (usageError) {
        throw usageError;
      }
      if (accountError) {
        throw accountError;
      }

      const snapshot = {
        plansData: plansData ?? [],
        usageData: usageData ?? null,
        accountData: accountData ?? null
      };

      billingCache = {
        scope,
        value: {
          value: snapshot,
          fetchedAt: Date.now()
        }
      };
      return snapshot;
    } catch (error) {
      assertAuthenticatedRequestScopeCurrent(scope);
      throw error;
    }
  })();

  const scopedRequest = { scope, value: request };
  billingRequest = scopedRequest;
  try {
    return await request;
  } finally {
    if (billingRequest === scopedRequest) {
      billingRequest = null;
    }
  }
}

export function getCachedSessionSnapshot(userId: string, sessionId: string): BriefingSessionResponse | null {
  const scope = currentScope(userId);
  const cached = sessionCache.get(sessionId);
  if (!scope || !cached || !scopesMatch(cached.scope, scope)) {
    return null;
  }

  if (Date.now() - cached.value.fetchedAt >= CACHE_TTL_MS) {
    sessionCache.delete(sessionId);
    return null;
  }

  return cached.value.value;
}

export function cacheSessionSnapshot(userId: string, snapshot: BriefingSessionResponse): void {
  const scope = captureAuthenticatedRequestScope(userId);
  sessionCache.set(String(snapshot.session_id), {
    scope,
    value: {
      value: snapshot,
      fetchedAt: Date.now()
    }
  });
}

export function evictSessionSnapshot(userId: string, sessionId: string): void {
  captureAuthenticatedRequestScope(userId);
  sessionCache.delete(sessionId);
}

export async function prefetchSessionSnapshot(
  userId: string,
  accessToken: string,
  sessionId: string
): Promise<BriefingSessionResponse | null> {
  const scope = captureAuthenticatedRequestScope(userId);
  const cached = getCachedSessionSnapshot(userId, sessionId);
  if (cached) {
    return cached;
  }

  const inFlight = sessionRequests.get(sessionId);
  if (inFlight && scopesMatch(inFlight.scope, scope)) {
    return inFlight.value;
  }

  const api = createApiClient(accessToken);
  const request = (async () => {
    try {
      const { data, error } = await api.GET("/briefing-sessions/{session_id}", {
        params: {
          path: {
            session_id: sessionId
          }
        }
      });

      assertAuthenticatedRequestScopeCurrent(scope);
      if (error) {
        throw error;
      }

      if (data) {
        cacheSessionSnapshot(userId, data);
        return data;
      }

      return null;
    } catch (error) {
      assertAuthenticatedRequestScopeCurrent(scope);
      throw error;
    }
  })();

  const scopedRequest = { scope, value: request };
  sessionRequests.set(sessionId, scopedRequest);
  try {
    return await request;
  } finally {
    if (sessionRequests.get(sessionId) === scopedRequest) {
      sessionRequests.delete(sessionId);
    }
  }
}

import type {
  BillingAccountResponse,
  BriefingSessionResponse,
  PlanResponse,
  UsageHistoryEntry,
  UsageOverviewResponse
} from "@fathom/api-client";
import { createApiClient } from "@fathom/api-client";

export type BillingSnapshot = {
  accountData: BillingAccountResponse | null;
  plansData: PlanResponse[];
  usageData: UsageOverviewResponse | null;
};

const CACHE_TTL_MS = 30_000;

let briefingsCache: { briefings: UsageHistoryEntry[]; fetchedAt: number } | null = null;
let briefingsRequest: Promise<UsageHistoryEntry[]> | null = null;

let billingCache: (BillingSnapshot & { fetchedAt: number }) | null = null;
let billingRequest: Promise<BillingSnapshot> | null = null;

let sessionCache = new Map<string, { snapshot: BriefingSessionResponse; fetchedAt: number }>();
let sessionRequests = new Map<string, Promise<BriefingSessionResponse | null>>();

export function getCachedBriefings(): UsageHistoryEntry[] | null {
  return briefingsCache?.briefings ?? null;
}

export function hasFreshBriefingsCache(): boolean {
  return Boolean(briefingsCache && Date.now() - briefingsCache.fetchedAt < CACHE_TTL_MS);
}

export async function loadBriefings(accessToken: string): Promise<UsageHistoryEntry[]> {
  if (briefingsRequest) {
    return briefingsRequest;
  }

  const api = createApiClient(accessToken);
  briefingsRequest = (async () => {
    const { data, error } = await api.GET("/billing/briefings");
    if (error) {
      throw error;
    }

    const briefings = data ?? [];
    briefingsCache = {
      briefings,
      fetchedAt: Date.now()
    };
    return briefings;
  })();

  try {
    return await briefingsRequest;
  } finally {
    briefingsRequest = null;
  }
}

export function getCachedBillingSnapshot(): BillingSnapshot | null {
  if (!billingCache) {
    return null;
  }

  return {
    plansData: billingCache.plansData,
    usageData: billingCache.usageData,
    accountData: billingCache.accountData
  };
}

export function hasFreshBillingCache(): boolean {
  return Boolean(billingCache && Date.now() - billingCache.fetchedAt < CACHE_TTL_MS);
}

export async function loadBillingSnapshot(accessToken: string): Promise<BillingSnapshot> {
  if (billingRequest) {
    return billingRequest;
  }

  const api = createApiClient(accessToken);
  billingRequest = (async () => {
    const [
      { data: plansData, error: plansError },
      { data: usageData, error: usageError },
      { data: accountData, error: accountError }
    ] = await Promise.all([api.GET("/billing/plans"), api.GET("/billing/usage"), api.GET("/billing/account")]);

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
      ...snapshot,
      fetchedAt: Date.now()
    };

    return snapshot;
  })();

  try {
    return await billingRequest;
  } finally {
    billingRequest = null;
  }
}

export function getCachedSessionSnapshot(sessionId: string): BriefingSessionResponse | null {
  const cached = sessionCache.get(sessionId);
  if (!cached) {
    return null;
  }

  if (Date.now() - cached.fetchedAt >= CACHE_TTL_MS) {
    sessionCache.delete(sessionId);
    return null;
  }

  return cached.snapshot;
}

export function cacheSessionSnapshot(snapshot: BriefingSessionResponse): void {
  sessionCache.set(String(snapshot.session_id), {
    snapshot,
    fetchedAt: Date.now()
  });
}

export async function prefetchSessionSnapshot(
  accessToken: string,
  sessionId: string
): Promise<BriefingSessionResponse | null> {
  const cached = getCachedSessionSnapshot(sessionId);
  if (cached) {
    return cached;
  }

  const inFlight = sessionRequests.get(sessionId);
  if (inFlight) {
    return inFlight;
  }

  const api = createApiClient(accessToken);
  const request = (async () => {
    const { data, error } = await api.GET("/briefing-sessions/{session_id}", {
      params: {
        path: {
          session_id: sessionId
        }
      }
    });

    if (error) {
      throw error;
    }

    if (data) {
      cacheSessionSnapshot(data);
      return data;
    }

    return null;
  })();

  sessionRequests.set(sessionId, request);
  try {
    return await request;
  } finally {
    sessionRequests.delete(sessionId);
  }
}

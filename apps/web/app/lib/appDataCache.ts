import type {
  BillingAccountResponse,
  BriefingSessionResponse,
  PlanResponse,
  UsageOverviewResponse
} from "@fathom/api-client";
import { createApiClient, getApiBaseUrl } from "@fathom/api-client";

import type { BriefingListResponse, BriefingsQueryOptions } from "./briefings";
import { DEFAULT_BRIEFINGS_QUERY } from "./briefings";

export type BillingSnapshot = {
  accountData: BillingAccountResponse | null;
  plansData: PlanResponse[];
  usageData: UsageOverviewResponse | null;
};

const CACHE_TTL_MS = 30_000;

let briefingsCache: { response: BriefingListResponse; fetchedAt: number } | null = null;
let briefingsRequest: Promise<BriefingListResponse> | null = null;

let billingCache: (BillingSnapshot & { fetchedAt: number }) | null = null;
let billingRequest: Promise<BillingSnapshot> | null = null;

let sessionCache = new Map<string, { snapshot: BriefingSessionResponse; fetchedAt: number }>();
let sessionRequests = new Map<string, Promise<BriefingSessionResponse | null>>();

export function getCachedBriefings(): BriefingListResponse | null {
  return briefingsCache?.response ?? null;
}

export function invalidateBriefingsCache(): void {
  briefingsCache = null;
}

export function hasFreshBriefingsCache(): boolean {
  return Boolean(briefingsCache && Date.now() - briefingsCache.fetchedAt < CACHE_TTL_MS);
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
  accessToken: string,
  options?: BriefingsQueryOptions
): Promise<BriefingListResponse> {
  const query = normalizeBriefingsQuery(options);
  const cacheable = isDefaultBriefingsQuery(query);

  if (cacheable && briefingsRequest) {
    return briefingsRequest;
  }

  const request = (async () => {
    const url = new URL("/briefings", getApiBaseUrl());
    url.searchParams.set("limit", String(query.limit));
    url.searchParams.set("offset", String(query.offset));
    url.searchParams.set("sort", query.sort);
    url.searchParams.set("sourceType", query.sourceType);

    if (query.query) {
      url.searchParams.set("query", query.query);
    }

    const response = await fetch(url.toString(), {
      headers: {
        Authorization: `Bearer ${accessToken}`
      }
    });
    const payload = (await response.json()) as BriefingListResponse | { message?: string };

    if (!response.ok) {
      throw payload;
    }

    if (cacheable) {
      briefingsCache = {
        response: payload as BriefingListResponse,
        fetchedAt: Date.now()
      };
    }

    return payload as BriefingListResponse;
  })();

  if (cacheable) {
    briefingsRequest = request;
  }

  try {
    return await request;
  } finally {
    if (cacheable) {
      briefingsRequest = null;
    }
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

export function evictSessionSnapshot(sessionId: string): void {
  sessionCache.delete(sessionId);
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

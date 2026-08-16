import type { UsageHistoryResponse } from "@fathom/api-client";

type UsageHistoryRequestResult = {
  data?: UsageHistoryResponse;
  error?: unknown;
};

export type OptionalUsageHistory = {
  data: UsageHistoryResponse | null;
  unavailable: boolean;
};

export async function loadOptionalUsageHistory(
  request: Promise<UsageHistoryRequestResult>
): Promise<OptionalUsageHistory> {
  try {
    const { data, error } = await request;
    if (error || !data) {
      return { data: null, unavailable: true };
    }
    return { data, unavailable: false };
  } catch {
    return { data: null, unavailable: true };
  }
}

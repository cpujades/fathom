import type { PackBillingState, UsageHistoryEntry, UsageOverviewResponse } from "@fathom/api-client";

type UsageBreakdownPart = {
  label: string;
  seconds: number;
};

export const getUsageBreakdown = (
  entry: Pick<UsageHistoryEntry, "subscription_seconds" | "pack_seconds" | "debt_incurred_seconds">
): UsageBreakdownPart[] => {
  return [
    { label: "Subscription", seconds: entry.subscription_seconds },
    { label: "Pack", seconds: entry.pack_seconds },
    { label: "Debt", seconds: entry.debt_incurred_seconds }
  ].filter((part) => part.seconds > 0);
};

export const mergeUsageHistoryEntries = (
  current: UsageHistoryEntry[],
  next: UsageHistoryEntry[]
): UsageHistoryEntry[] => {
  const entriesByJobId = new Map(current.map((entry) => [entry.job_id, entry]));
  for (const entry of next) {
    entriesByJobId.set(entry.job_id, entry);
  }
  return [...entriesByJobId.values()];
};

export const getDisplayedPacks = (packs: PackBillingState[]): PackBillingState[] => {
  return packs.filter((pack) => pack.status !== "refunded");
};

export const applyPendingRefundHold = (
  usage: UsageOverviewResponse,
  requestedHoldSeconds: number
): UsageOverviewResponse => {
  const heldSeconds = Math.min(
    Math.max(Math.trunc(requestedHoldSeconds), 0),
    Math.max(usage.pack_remaining_seconds, 0)
  );

  return {
    ...usage,
    pack_remaining_seconds: Math.max(usage.pack_remaining_seconds - heldSeconds, 0),
    total_remaining_seconds: Math.max(usage.total_remaining_seconds - heldSeconds, 0)
  };
};

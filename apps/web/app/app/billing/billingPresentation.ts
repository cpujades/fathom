import type { PackBillingState, UsageOverviewResponse } from "@fathom/api-client";

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

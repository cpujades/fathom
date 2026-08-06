export const LOW_BALANCE_WARNING_SECONDS = 600;
export const USAGE_SNAPSHOT_STALE_MS = 30_000;

export type UsageBalance = {
  debt_seconds: number;
  is_blocked: boolean;
  total_remaining_seconds: number;
};

type SharedUsageBalance = {
  debtSeconds: number | null;
  isBlocked: boolean | null;
  remainingSeconds: number | null;
};

type UsageSnapshotAge = {
  fetchedAt: number;
};

export type BillingOffersAction = {
  href: string;
  label: string;
};

export function getBillingOffersAction(
  hasActivePaidSubscription: boolean | null | undefined
): BillingOffersAction {
  return hasActivePaidSubscription
    ? {
        href: "/app/billing?view=packs#billing-offers",
        label: "Add a one-time pack"
      }
    : {
        href: "/app/billing#billing-offers",
        label: "See plans and packs"
      };
}

export function getLowBalanceSeconds(usage: UsageBalance | null): number | null {
  if (
    !usage ||
    usage.is_blocked ||
    usage.debt_seconds > 0 ||
    usage.total_remaining_seconds <= 0 ||
    usage.total_remaining_seconds >= LOW_BALANCE_WARNING_SECONDS
  ) {
    return null;
  }
  return usage.total_remaining_seconds;
}

export function resolveCurrentUsageBalance(
  loadedUsage: UsageBalance | null,
  sharedUsage: SharedUsageBalance
): UsageBalance | null {
  if (
    sharedUsage.remainingSeconds === null ||
    sharedUsage.debtSeconds === null ||
    sharedUsage.isBlocked === null
  ) {
    return loadedUsage;
  }

  return {
    debt_seconds: sharedUsage.debtSeconds,
    is_blocked: sharedUsage.isBlocked,
    total_remaining_seconds: sharedUsage.remainingSeconds
  };
}

export function isUsageSnapshotStale(
  snapshot: UsageSnapshotAge | null,
  now: number
): boolean {
  return !snapshot || now - snapshot.fetchedAt >= USAGE_SNAPSHOT_STALE_MS;
}

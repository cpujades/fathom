import type { BillingOrderHistoryEntry, PackBillingState, PlanResponse } from "@fathom/api-client";

import chrome from "../../components/app-chrome";

export type PlanGroup = {
  key: "subscription" | "pack";
  label: string;
  description: string;
  plans: PlanResponse[];
};

export type PurchaseSyncState = {
  status: "syncing" | "synced" | "delayed";
  orderLabel: string | null;
};

export type RefundSyncState = {
  orderId: string;
  orderLabel: string | null;
  status: "syncing" | "synced" | "delayed";
};

export function formatPrice(amountCents: number, currency: string, billingInterval: string | null): string {
  if (amountCents <= 0) return "Free";
  const amount = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase()
  }).format(amountCents / 100);
  return billingInterval ? `${amount}/${billingInterval}` : amount;
}

export function describeSubscriptionStatus(status: string | null): string {
  if (!status) return "No active subscription";
  if (status === "active") return "Active";
  if (status === "canceled") return "Cancels at period end";
  if (status === "revoked") return "Revoked";
  return status.replaceAll("_", " ");
}

export function getStatusTone(status: string | null): string {
  if (status === "active" || status === "paid" || status === "refunded") return chrome.statusPillSuccess;
  if (status === "refund_pending" || status === "canceled") return chrome.statusPillWarning;
  if (status === "revoked") return chrome.statusPillDanger;
  return chrome.statusPillMuted;
}

export function getOrderLabel(
  order:
    | Pick<BillingOrderHistoryEntry, "plan_name" | "plan_type">
    | Pick<PackBillingState, "plan_name">
    | null
    | undefined
): string | null {
  if (!order) return null;
  if (order.plan_name) return order.plan_name;
  return "plan_type" in order ? (order.plan_type === "subscription" ? "Subscription" : "Pack") : "Pack";
}

export function getPlanBadge(plan: PlanResponse, groupKey: PlanGroup["key"]): string | null {
  const normalizedName = plan.name.toLowerCase();
  if (groupKey === "subscription") {
    if (normalizedName.includes("starter")) return "Recommended";
    if (normalizedName.includes("pro")) return "Best value";
    if (normalizedName.includes("agency")) return "High volume";
    return null;
  }
  if (normalizedName.includes("creator")) return "Flexible";
  if (normalizedName.includes("studio")) return "Best value";
  return null;
}

export function findRecentOrder(
  orders: BillingOrderHistoryEntry[],
  checkoutStartedAt: number | null
): BillingOrderHistoryEntry | null {
  if (!checkoutStartedAt) return null;
  const threshold = checkoutStartedAt - 120_000;
  return (
    [...orders]
      .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())
      .find((entry) => new Date(entry.created_at).getTime() >= threshold) ?? null
  );
}

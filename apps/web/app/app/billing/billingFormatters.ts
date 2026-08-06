import type { BillingOrderHistoryEntry, PackBillingState, PlanResponse } from "@fathom/api-client";

import chrome from "../../components/app-chrome";

export type PlanGroup = {
  key: "subscription" | "pack";
  label: string;
  description: string;
  plans: PlanResponse[];
};

export type PurchaseSyncState = {
  status: "syncing" | "synced" | "failed" | "delayed";
  snapshotStatus: "idle" | "refreshing" | "current" | "unavailable";
  orderLabel: string | null;
  failureCode: string | null;
};

export type RefundSyncState = {
  orderLabel: string | null;
  status: "syncing" | "synced" | "failed" | "delayed";
  snapshotStatus: "idle" | "refreshing" | "current" | "unavailable";
  failureCode: string | null;
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
  if (status === "canceled") return "Canceled";
  if (status === "revoked") return "Revoked";
  return status.replaceAll("_", " ");
}

export function getStatusTone(status: string | null): string {
  if (status === "active" || status === "paid" || status === "refunded") return chrome.statusPillSuccess;
  if (status === "refund_pending") return chrome.statusPillWarning;
  if (status === "canceled" || status === "revoked") return chrome.statusPillDanger;
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

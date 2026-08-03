"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import type { BillingAccountResponse, PackBillingState, PlanResponse, UsageOverviewResponse } from "@fathom/api-client";
import { createApiClient } from "@fathom/api-client";

import { useAppShell } from "../../components/AppShellProvider";
import { getApiErrorMessage } from "../../lib/apiErrors";
import {
  assertAuthenticatedRequestScopeCurrent,
  captureAuthenticatedRequestScope,
  getCachedBillingSnapshot,
  hasFreshBillingCache,
  loadBillingSnapshot
} from "../../lib/appDataCache";
import { formatDate } from "../../lib/format";
import {
  describeSubscriptionStatus,
  findRecentOrder,
  getOrderLabel,
  type PlanGroup,
  type PurchaseSyncState,
  type RefundSyncState
} from "./billingFormatters";
import { resolveRequestedPlan } from "./billingIntent";
import { applyPendingRefundHold, getDisplayedPacks } from "./billingPresentation";

export function useBillingController() {
  const searchParams = useSearchParams();
  const { accessToken, loading: shellLoading, remainingSeconds, setRemainingSeconds, signOut, user } = useAppShell();
  const userId = user?.id ?? null;
  const checkoutStatus = searchParams.get("checkout");
  const customerSessionToken = searchParams.get("customer_session_token");
  const requestedIntent = searchParams.get("intent");
  const requestedPlanCode = searchParams.get("plan");
  const cachedSnapshot = userId ? getCachedBillingSnapshot(userId) : null;

  const [plans, setPlans] = useState<PlanResponse[]>(cachedSnapshot?.plansData ?? []);
  const [usage, setUsage] = useState<UsageOverviewResponse | null>(cachedSnapshot?.usageData ?? null);
  const [account, setAccount] = useState<BillingAccountResponse | null>(cachedSnapshot?.accountData ?? null);
  const [loading, setLoading] = useState(() => cachedSnapshot === null);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [refundLoading, setRefundLoading] = useState<string | null>(null);
  const [refundTarget, setRefundTarget] = useState<PackBillingState | null>(null);
  const [offerMode, setOfferMode] = useState<"subscription" | "pack">("subscription");
  const [purchaseSync, setPurchaseSync] = useState<PurchaseSyncState | null>(null);
  const [refundSync, setRefundSync] = useState<RefundSyncState | null>(null);
  const [syncRefreshLoading, setSyncRefreshLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const checkoutStartRef = useRef<number | null>(null);
  const focusedPlanRef = useRef<string | null>(null);
  const refundPollRef = useRef<number | null>(null);

  const loadBilling = useCallback(async (showLoading: boolean) => {
    if (!accessToken || !userId) return null;
    if (showLoading) setLoading(true);
    try {
      const snapshot = await loadBillingSnapshot(userId, accessToken);
      setPlans(snapshot.plansData);
      setUsage(snapshot.usageData);
      setAccount(snapshot.accountData);
      setRemainingSeconds(userId, snapshot.usageData?.total_remaining_seconds ?? null);
      setError(null);
      return snapshot;
    } catch (loadError) {
      setError(getApiErrorMessage(loadError, "Unable to load billing details."));
      return null;
    } finally {
      if (showLoading) setLoading(false);
    }
  }, [accessToken, setRemainingSeconds, userId]);

  useEffect(() => {
    if (!accessToken || !userId) return;
    if (hasFreshBillingCache(userId)) {
      const nextSnapshot = getCachedBillingSnapshot(userId);
      setPlans(nextSnapshot?.plansData ?? []);
      setUsage(nextSnapshot?.usageData ?? null);
      setAccount(nextSnapshot?.accountData ?? null);
      setLoading(false);
      setError(null);
      return;
    }
    void loadBilling(cachedSnapshot === null);
  }, [accessToken, cachedSnapshot, loadBilling, userId]);

  useEffect(() => {
    if (checkoutStatus !== "success") return;
    checkoutStartRef.current ??= Date.now();
    setPurchaseSync({ status: "syncing", orderLabel: null });

    let attempts = 0;
    const timer = window.setInterval(async () => {
      attempts += 1;
      const result = await loadBilling(false);
      const recentOrder = findRecentOrder(result?.accountData?.orders ?? [], checkoutStartRef.current);
      if (recentOrder) {
        setPurchaseSync({ status: "synced", orderLabel: getOrderLabel(recentOrder) });
        window.clearInterval(timer);
      } else if (attempts >= 20) {
        setPurchaseSync((current) => ({ status: "delayed", orderLabel: current?.orderLabel ?? null }));
        window.clearInterval(timer);
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [checkoutStatus, customerSessionToken, loadBilling]);

  useEffect(() => () => {
    if (refundPollRef.current !== null) window.clearInterval(refundPollRef.current);
  }, []);

  const planGroups = useMemo<PlanGroup[]>(() => [
    {
      key: "subscription",
      label: "Monthly subscriptions",
      description: "Best for steady use and recurring briefing volume.",
      plans: plans.filter((plan) => plan.plan_type === "subscription")
    },
    {
      key: "pack",
      label: "One-time packs",
      description: "Add video time when you need it without a recurring charge.",
      plans: plans.filter((plan) => plan.plan_type === "pack")
    }
  ], [plans]);

  const requestedPlan = useMemo(
    () => resolveRequestedPlan(plans, requestedIntent, requestedPlanCode),
    [plans, requestedIntent, requestedPlanCode]
  );

  useEffect(() => {
    if (requestedPlan) setOfferMode(requestedPlan.plan_type === "pack" ? "pack" : "subscription");
  }, [requestedPlan]);

  useEffect(() => {
    if (!requestedPlan || focusedPlanRef.current === requestedPlan.plan_id) return;
    const expectedMode = requestedPlan.plan_type === "pack" ? "pack" : "subscription";
    if (offerMode !== expectedMode) return;

    const frameId = window.requestAnimationFrame(() => {
      const planCard = document.getElementById(`billing-plan-${requestedPlan.plan_id}`);
      planCard?.focus({ preventScroll: true });
      planCard?.scrollIntoView({ behavior: "smooth", block: "center" });
      focusedPlanRef.current = requestedPlan.plan_id;
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [offerMode, requestedPlan]);

  const displayedPacks = useMemo(() => getDisplayedPacks(account?.packs ?? []), [account?.packs]);
  const activePackCount = useMemo(
    () => displayedPacks.filter((pack) => pack.remaining_seconds > 0 && pack.status === "paid").length,
    [displayedPacks]
  );
  const currentSubscriptionPlan = useMemo(() => {
    const planName = account?.subscription.plan_name ?? usage?.subscription_plan_name ?? null;
    return planName
      ? plans.find((plan) => plan.plan_type === "subscription" && plan.name.toLowerCase() === planName.toLowerCase()) ?? null
      : null;
  }, [account?.subscription.plan_name, plans, usage?.subscription_plan_name]);
  const quotaCapacitySeconds = useMemo(() => {
    if (!usage) return 0;
    const subscriptionQuota = currentSubscriptionPlan?.quota_seconds ?? usage.subscription_remaining_seconds;
    const packAllowance = displayedPacks
      .filter((pack) => pack.status === "paid" && pack.remaining_seconds > 0)
      .reduce((total, pack) => total + pack.granted_seconds, 0);
    return Math.max(subscriptionQuota + packAllowance, usage.total_remaining_seconds);
  }, [currentSubscriptionPlan?.quota_seconds, displayedPacks, usage]);
  const quotaAvailablePercent = useMemo(() => {
    if (!usage || quotaCapacitySeconds <= 0) return null;
    return Math.max(0, Math.min(100, Math.round((usage.total_remaining_seconds / quotaCapacitySeconds) * 100)));
  }, [quotaCapacitySeconds, usage]);
  const canManageBilling = useMemo(
    () => (account?.orders ?? []).some((order) => order.paid_amount_cents > 0),
    [account?.orders]
  );
  const subscriptionStatusText = describeSubscriptionStatus(account?.subscription.status ?? null);
  const accessNote = useMemo(() => {
    if ((usage?.pack_remaining_seconds ?? 0) > 0 && usage?.pack_expires_at) {
      return `One-time pack balance expires ${formatDate(usage.pack_expires_at)}.`;
    }
    const planName = account?.subscription.plan_name ?? usage?.subscription_plan_name;
    if (planName && planName.toLowerCase() !== "free" && account?.subscription.period_end) {
      return `Current plan renews ${formatDate(account.subscription.period_end)}.`;
    }
    return "Add more video time whenever you need it.";
  }, [account?.subscription.period_end, account?.subscription.plan_name, usage?.pack_expires_at, usage?.pack_remaining_seconds, usage?.subscription_plan_name]);
  const visiblePlanGroup = useMemo(
    () => planGroups.find((group) => group.key === offerMode) ?? null,
    [offerMode, planGroups]
  );

  const handleCheckout = async (planId: string) => {
    if (checkoutLoading) return;
    setCheckoutLoading(planId);
    setError(null);
    try {
      if (!accessToken || !userId) return;
      const scope = captureAuthenticatedRequestScope(userId);
      const { data, error: apiError } = await createApiClient(accessToken).POST("/billing/checkout", {
        body: { plan_id: planId }
      });
      assertAuthenticatedRequestScopeCurrent(scope);
      if (apiError) setError(getApiErrorMessage(apiError, "Unable to start checkout."));
      else if (data?.checkout_url) window.location.href = data.checkout_url;
    } catch (checkoutError) {
      setError(checkoutError instanceof Error ? checkoutError.message : "Something went wrong.");
    } finally {
      setCheckoutLoading(null);
    }
  };

  const handlePortal = async () => {
    if (portalLoading) return;
    setPortalLoading(true);
    setError(null);
    try {
      if (!accessToken || !userId) return;
      const scope = captureAuthenticatedRequestScope(userId);
      const { data, error: apiError } = await createApiClient(accessToken).POST("/billing/portal");
      assertAuthenticatedRequestScopeCurrent(scope);
      if (apiError) setError(getApiErrorMessage(apiError, "Unable to open billing portal."));
      else if (data?.portal_url) window.location.href = data.portal_url;
    } catch (portalError) {
      setError(portalError instanceof Error ? portalError.message : "Something went wrong.");
    } finally {
      setPortalLoading(false);
    }
  };

  const handleRefund = async (polarOrderId: string): Promise<boolean> => {
    if (refundLoading) return false;
    setRefundLoading(polarOrderId);
    setError(null);
    try {
      if (!accessToken || !userId) return false;
      const scope = captureAuthenticatedRequestScope(userId);
      const { data, error: apiError } = await createApiClient(accessToken).POST(
        "/billing/packs/{polar_order_id}/refund",
        { params: { path: { polar_order_id: polarOrderId } } }
      );
      assertAuthenticatedRequestScopeCurrent(scope);
      if (apiError) {
        setError(getApiErrorMessage(apiError, "Unable to request pack refund."));
        return false;
      }

      if (usage && data?.remaining_seconds_before_refund) {
        const nextUsage = applyPendingRefundHold(usage, data.remaining_seconds_before_refund);
        setUsage(nextUsage);
        setRemainingSeconds(userId, nextUsage.total_remaining_seconds);
      }
      setAccount((previous) => previous ? {
        ...previous,
        packs: previous.packs.map((pack) => pack.polar_order_id === polarOrderId
          ? { ...pack, status: "refund_pending", is_refundable: false, refundable_amount_cents: 0 }
          : pack),
        orders: previous.orders.map((order) => order.polar_order_id === polarOrderId
          ? { ...order, status: "refund_pending" }
          : order)
      } : previous);

      const order = account?.orders.find((item) => item.polar_order_id === polarOrderId)
        ?? account?.packs.find((item) => item.polar_order_id === polarOrderId)
        ?? null;
      setRefundSync({ orderId: polarOrderId, orderLabel: getOrderLabel(order), status: "syncing" });
      if (refundPollRef.current !== null) window.clearInterval(refundPollRef.current);

      let attempts = 0;
      refundPollRef.current = window.setInterval(async () => {
        attempts += 1;
        const result = await loadBilling(false);
        const status = result?.accountData?.orders.find((item) => item.polar_order_id === polarOrderId)?.status;
        if (status === "refunded" || attempts >= 24) {
          if (refundPollRef.current !== null) window.clearInterval(refundPollRef.current);
          refundPollRef.current = null;
          setRefundSync((current) => current ? { ...current, status: status === "refunded" ? "synced" : "delayed" } : null);
        }
      }, 2500);
      return true;
    } catch (refundError) {
      setError(getApiErrorMessage(refundError, "Unable to request pack refund."));
      return false;
    } finally {
      setRefundLoading(null);
    }
  };

  const handleConfirmRefund = async () => {
    if (refundTarget && await handleRefund(refundTarget.polar_order_id)) setRefundTarget(null);
  };

  const handleRefreshSyncStatus = useCallback(async () => {
    if (syncRefreshLoading) return;
    setSyncRefreshLoading(true);
    try {
      const orders = (await loadBilling(false))?.accountData?.orders ?? [];
      if (purchaseSync) {
        const recentOrder = findRecentOrder(orders, checkoutStartRef.current);
        if (recentOrder) setPurchaseSync({ status: "synced", orderLabel: getOrderLabel(recentOrder) });
      }
      if (refundSync) {
        const matchingOrder = orders.find((order) => order.polar_order_id === refundSync.orderId);
        if (matchingOrder?.status === "refunded") {
          setRefundSync({ ...refundSync, orderLabel: refundSync.orderLabel ?? getOrderLabel(matchingOrder), status: "synced" });
        }
      }
    } finally {
      setSyncRefreshLoading(false);
    }
  }, [loadBilling, purchaseSync, refundSync, syncRefreshLoading]);

  const selectRefundTarget = (pack: PackBillingState) => {
    setError(null);
    setRefundTarget(pack);
  };
  const closeRefundDialog = () => {
    if (refundLoading === null) setRefundTarget(null);
  };

  return {
    accessNote, account, activePackCount, canManageBilling, checkoutLoading, closeRefundDialog, displayedPacks,
    error, handleCheckout, handleConfirmRefund, handlePortal, handleRefreshSyncStatus, loading, offerMode,
    portalLoading, purchaseSync, quotaAvailablePercent, quotaCapacitySeconds, refundLoading, refundSync,
    refundTarget, remainingSeconds, requestedPlan, selectRefundTarget, setOfferMode, shellLoading, signOut,
    subscriptionStatusText, syncRefreshLoading, usage, user, visiblePlanGroup
  };
}

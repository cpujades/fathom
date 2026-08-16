"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import type {
  BillingAccountResponse,
  BillingSyncOperationResponse,
  PackBillingState,
  PlanResponse,
  UsageHistoryEntry,
  UsageOverviewResponse
} from "@fathom/api-client";
import { createApiClient } from "@fathom/api-client";

import { useAppShell } from "../../components/AppShellProvider";
import { getApiErrorMessage } from "../../lib/apiErrors";
import {
  assertAuthenticatedRequestScopeCurrent,
  captureAuthenticatedRequestScope,
  getCachedBillingSnapshot,
  hasFreshBillingCache,
  isAuthenticatedDataScopeChangedError,
  loadBillingSnapshot,
  USAGE_HISTORY_PAGE_SIZE
} from "../../lib/appDataCache";
import { formatDate } from "../../lib/format";
import {
  describeSubscriptionStatus,
  getOrderLabel,
  type PlanGroup,
  type PurchaseSyncState,
  type RefundSyncState
} from "./billingFormatters";
import { resolveBillingOfferMode, resolveRequestedPlan } from "./billingIntent";
import {
  BillingOperationReadError,
  type CompletedBillingOperationPoll,
  handleBillingSyncRefresh,
  manuallyRefreshBillingOperation,
  pollBillingOperationAndRefreshSnapshot,
  setBillingOperationInUrl
} from "./billingOperationSync";
import { applyPendingRefundHold, getDisplayedPacks, mergeUsageHistoryEntries } from "./billingPresentation";

type BillingSyncTarget = {
  operationId: string;
  expectedType: "checkout" | "refund" | null;
  orderLabel: string | null;
};

const USAGE_HISTORY_UNAVAILABLE_MESSAGE =
  "Usage history is temporarily unavailable. Your plans and balance are still available.";

export function useBillingController() {
  const searchParams = useSearchParams();
  const { accessToken, loading: shellLoading, remainingSeconds, setRemainingSeconds, signOut, user } = useAppShell();
  const userId = user?.id ?? null;
  const checkoutStatus = searchParams.get("checkout");
  const billingOperationId = searchParams.get("billing_operation");
  const requestedIntent = searchParams.get("intent");
  const requestedPlanCode = searchParams.get("plan");
  const requestedView = searchParams.get("view");
  const cachedSnapshot = userId ? getCachedBillingSnapshot(userId) : null;

  const [plans, setPlans] = useState<PlanResponse[]>(cachedSnapshot?.plansData ?? []);
  const [usage, setUsage] = useState<UsageOverviewResponse | null>(cachedSnapshot?.usageData ?? null);
  const [usageHistory, setUsageHistory] = useState<UsageHistoryEntry[]>(cachedSnapshot?.usageHistoryData ?? []);
  const [usageHistoryHasMore, setUsageHistoryHasMore] = useState(cachedSnapshot?.usageHistoryHasMore ?? false);
  const [usageHistoryLoadingMore, setUsageHistoryLoadingMore] = useState(false);
  const [usageHistoryError, setUsageHistoryError] = useState<string | null>(
    cachedSnapshot?.usageHistoryUnavailable ? USAGE_HISTORY_UNAVAILABLE_MESSAGE : null
  );
  const [account, setAccount] = useState<BillingAccountResponse | null>(cachedSnapshot?.accountData ?? null);
  const [loading, setLoading] = useState(() => cachedSnapshot === null);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [refundLoading, setRefundLoading] = useState<string | null>(null);
  const [refundTarget, setRefundTarget] = useState<PackBillingState | null>(null);
  const [offerMode, setOfferMode] = useState<"subscription" | "pack">(
    () => resolveBillingOfferMode(requestedView)
  );
  const [purchaseSync, setPurchaseSync] = useState<PurchaseSyncState | null>(null);
  const [refundSync, setRefundSync] = useState<RefundSyncState | null>(null);
  const [syncRefreshLoading, setSyncRefreshLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeSyncRef = useRef<BillingSyncTarget | null>(null);
  const operationAbortRef = useRef<AbortController | null>(null);
  const focusedPlanRef = useRef<string | null>(null);

  const loadBilling = useCallback(async (showLoading: boolean, refreshAfterInFlight = false) => {
    if (!accessToken || !userId) return null;
    if (showLoading) setLoading(true);
    try {
      const snapshot = await loadBillingSnapshot(userId, accessToken, { refreshAfterInFlight });
      setPlans(snapshot.plansData);
      setUsage(snapshot.usageData);
      setUsageHistory(snapshot.usageHistoryData);
      setUsageHistoryHasMore(snapshot.usageHistoryHasMore);
      setUsageHistoryError(
        snapshot.usageHistoryUnavailable ? USAGE_HISTORY_UNAVAILABLE_MESSAGE : null
      );
      setAccount(snapshot.accountData);
      setRemainingSeconds(
        userId,
        snapshot.usageData?.total_remaining_seconds ?? null,
        snapshot.usageData?.has_active_paid_subscription ?? null,
        snapshot.usageData?.debt_seconds ?? null,
        snapshot.usageData?.is_blocked ?? null
      );
      setError(null);
      return snapshot;
    } catch (loadError) {
      setError(getApiErrorMessage(loadError, "Unable to load billing details."));
      return null;
    } finally {
      if (showLoading) setLoading(false);
    }
  }, [accessToken, setRemainingSeconds, userId]);

  const loadBillingOperation = useCallback(async (operationId: string, signal: AbortSignal) => {
    if (!accessToken || !userId) return null;
    const scope = captureAuthenticatedRequestScope(userId);
    let result;
    try {
      result = await createApiClient(accessToken).GET(
        "/billing/operations/{operation_id}",
        { params: { path: { operation_id: operationId } }, signal }
      );
    } catch (readError) {
      if (signal.aborted) throw readError;
      throw new BillingOperationReadError(
        getApiErrorMessage(readError, "Unable to reach billing confirmation."),
        true
      );
    }
    const { data, error: apiError, response } = result;
    assertAuthenticatedRequestScopeCurrent(scope);
    if (apiError) {
      const status = response.status;
      const retryable = status === 408 || status === 425 || status === 429 || status >= 500;
      throw new BillingOperationReadError(
        getApiErrorMessage(apiError, "Unable to check billing confirmation."),
        retryable
      );
    }
    return data ?? null;
  }, [accessToken, userId]);

  const showOperationState = useCallback((
    operationType: BillingSyncOperationResponse["operation_type"],
    status: "syncing" | "synced" | "failed" | "delayed",
    orderLabel: string | null,
    failureCode: string | null = null,
    snapshotStatus: PurchaseSyncState["snapshotStatus"] = "idle"
  ) => {
    const nextState = { status, orderLabel, failureCode, snapshotStatus };
    if (operationType === "checkout") {
      setPurchaseSync((current) => (
        current?.status === status && current.orderLabel === orderLabel && current.failureCode === failureCode
          && current.snapshotStatus === snapshotStatus
          ? current
          : nextState
      ));
    } else {
      setRefundSync((current) => (
        current?.status === status && current.orderLabel === orderLabel && current.failureCode === failureCode
          && current.snapshotStatus === snapshotStatus
          ? current
          : nextState
      ));
    }
  }, []);

  const startBillingOperationSync = useCallback(async (
    target: BillingSyncTarget,
    mode: "automatic" | "manual" = "automatic"
  ) => {
    operationAbortRef.current?.abort();
    const abortController = new AbortController();
    operationAbortRef.current = abortController;
    activeSyncRef.current = target;

    if (target.expectedType) {
      showOperationState(target.expectedType, "syncing", target.orderLabel);
    }

    const refreshOptions = {
      signal: abortController.signal,
      onOperation: (operation: BillingSyncOperationResponse) => {
        showOperationState(operation.operation_type, "syncing", target.orderLabel);
      },
      shouldRefreshSnapshot: () => activeSyncRef.current?.operationId === target.operationId,
      onBeforeSnapshotRefresh: (result: CompletedBillingOperationPoll) => {
        const operationType = result.operation?.operation_type ?? target.expectedType;
        if (operationType) {
          showOperationState(
            operationType,
            result.outcome === "terminal"
              ? (result.operation.status === "succeeded" ? "synced" : "failed")
              : "delayed",
            target.orderLabel,
            result.outcome === "terminal" ? result.operation.failure_code : null,
            "refreshing"
          );
        }
      }
    };
    const refreshedResult = mode === "manual"
      ? await manuallyRefreshBillingOperation(
          (signal) => loadBillingOperation(target.operationId, signal),
          () => loadBilling(false, true),
          refreshOptions
        )
      : await pollBillingOperationAndRefreshSnapshot(
          (signal) => loadBillingOperation(target.operationId, signal),
          () => loadBilling(false, true),
          refreshOptions
        );
    if (refreshedResult.outcome === "aborted"
      || activeSyncRef.current?.operationId !== target.operationId) return;

    const operationType = refreshedResult.operation?.operation_type ?? target.expectedType;

    if (refreshedResult.outcome === "timeout") {
      if (operationType) {
        showOperationState(
          operationType,
          "delayed",
          target.orderLabel,
          null,
          refreshedResult.snapshotStatus
        );
      }
      return;
    }
    if (refreshedResult.outcome === "read_failed") {
      if (operationType) {
        showOperationState(
          operationType,
          "delayed",
          target.orderLabel,
          null,
          refreshedResult.snapshotStatus
        );
      }
      if (!operationType) {
        setError(getApiErrorMessage(
          refreshedResult.error,
          "Unable to check billing confirmation. The billing details below were refreshed separately."
        ));
      }
      return;
    }

    const { operation, snapshotStatus } = refreshedResult;
    showOperationState(
      operation.operation_type,
      operation.status === "succeeded" ? "synced" : "failed",
      target.orderLabel,
      operation.failure_code,
      snapshotStatus
    );
    activeSyncRef.current = null;
    setBillingOperationInUrl(null);
  }, [loadBilling, loadBillingOperation, showOperationState]);

  useEffect(() => {
    if (!accessToken || !userId) return;
    if (hasFreshBillingCache(userId)) {
      const nextSnapshot = getCachedBillingSnapshot(userId);
      setPlans(nextSnapshot?.plansData ?? []);
      setUsage(nextSnapshot?.usageData ?? null);
      setUsageHistory(nextSnapshot?.usageHistoryData ?? []);
      setUsageHistoryHasMore(nextSnapshot?.usageHistoryHasMore ?? false);
      setUsageHistoryError(
        nextSnapshot?.usageHistoryUnavailable ? USAGE_HISTORY_UNAVAILABLE_MESSAGE : null
      );
      setAccount(nextSnapshot?.accountData ?? null);
      setLoading(false);
      setError(null);
      return;
    }
    void loadBilling(cachedSnapshot === null);
  }, [accessToken, cachedSnapshot, loadBilling, userId]);

  useEffect(() => {
    if (!billingOperationId) {
      if (checkoutStatus === "success") {
        setPurchaseSync({ status: "delayed", orderLabel: null, failureCode: null, snapshotStatus: "idle" });
      }
      return;
    }
    if (activeSyncRef.current?.operationId === billingOperationId) return;

    const target: BillingSyncTarget = {
      operationId: billingOperationId,
      expectedType: checkoutStatus === "success" ? "checkout" : null,
      orderLabel: null
    };
    void startBillingOperationSync(target);
    return () => {
      if (activeSyncRef.current?.operationId === billingOperationId) {
        operationAbortRef.current?.abort();
      }
    };
  }, [billingOperationId, checkoutStatus, startBillingOperationSync]);

  useEffect(() => () => operationAbortRef.current?.abort(), []);

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
    if (!requestedPlan) {
      setOfferMode(resolveBillingOfferMode(requestedView));
    }
  }, [requestedPlan, requestedView]);

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
      if (!data?.operation_id) {
        setError("The refund was requested, but Talven could not track its confirmation yet.");
        return false;
      }

      if (usage && data?.remaining_seconds_before_refund) {
        const nextUsage = applyPendingRefundHold(usage, data.remaining_seconds_before_refund);
        setUsage(nextUsage);
        setRemainingSeconds(
          userId,
          nextUsage.total_remaining_seconds,
          nextUsage.has_active_paid_subscription,
          nextUsage.debt_seconds,
          nextUsage.is_blocked
        );
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
      const syncTarget: BillingSyncTarget = {
        operationId: data.operation_id,
        expectedType: "refund",
        orderLabel: getOrderLabel(order)
      };
      setBillingOperationInUrl(data.operation_id);
      void startBillingOperationSync(syncTarget);
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

  const handleLoadMoreUsageHistory = async () => {
    if (!accessToken || !userId || usageHistoryLoadingMore || !usageHistoryHasMore) return;

    setUsageHistoryLoadingMore(true);
    try {
      const scope = captureAuthenticatedRequestScope(userId);
      const { data, error: apiError } = await createApiClient(accessToken).GET("/billing/usage-history", {
        params: {
          query: {
            limit: USAGE_HISTORY_PAGE_SIZE,
            offset: usageHistory.length
          }
        }
      });
      assertAuthenticatedRequestScopeCurrent(scope);
      if (apiError) throw apiError;
      if (!data) throw new Error("The usage history response was empty.");

      setUsageHistory((current) => mergeUsageHistoryEntries(current, data.items));
      setUsageHistoryHasMore(data.has_more);
      setUsageHistoryError(null);
    } catch (historyError) {
      if (isAuthenticatedDataScopeChangedError(historyError)) return;
      setUsageHistoryError(getApiErrorMessage(historyError, "Unable to load more usage history."));
    } finally {
      setUsageHistoryLoadingMore(false);
    }
  };

  const handleRefreshSyncStatus = useCallback(async () => {
    if (syncRefreshLoading) return;
    setSyncRefreshLoading(true);
    try {
      await handleBillingSyncRefresh({
        target: activeSyncRef.current,
        refreshOperation: startBillingOperationSync,
        refreshSnapshot: () => loadBilling(false, true),
        onSnapshotStatus: (snapshotStatus) => {
          setPurchaseSync((current) => current ? { ...current, snapshotStatus } : current);
          setRefundSync((current) => current ? { ...current, snapshotStatus } : current);
        }
      });
    } finally {
      setSyncRefreshLoading(false);
    }
  }, [loadBilling, startBillingOperationSync, syncRefreshLoading]);

  const selectRefundTarget = (pack: PackBillingState) => {
    setError(null);
    setRefundTarget(pack);
  };
  const closeRefundDialog = () => {
    if (refundLoading === null) setRefundTarget(null);
  };

  return {
    accessNote, account, activePackCount, canManageBilling, checkoutLoading, closeRefundDialog, displayedPacks,
    error, handleCheckout, handleConfirmRefund, handleLoadMoreUsageHistory, handlePortal, handleRefreshSyncStatus,
    loading, offerMode,
    portalLoading, purchaseSync, quotaAvailablePercent, quotaCapacitySeconds, refundLoading, refundSync,
    refundTarget, remainingSeconds, requestedPlan, selectRefundTarget, setOfferMode, shellLoading, signOut,
    subscriptionStatusText, syncRefreshLoading, usage, usageHistory, usageHistoryError, usageHistoryHasMore,
    usageHistoryLoadingMore, user, visiblePlanGroup
  };
}

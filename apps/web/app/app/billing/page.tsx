"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import type {
  BillingAccountResponse,
  BillingOrderHistoryEntry,
  PackBillingState,
  PlanResponse,
  UsageOverviewResponse
} from "@fathom/api-client";
import { createApiClient } from "@fathom/api-client";

import { AppShellHeader } from "../../components/AppShellHeader";
import { useAppShell } from "../../components/AppShellProvider";
import chrome from "../../components/app-chrome.module.css";
import styles from "./billing.module.css";
import { formatDate, formatDuration } from "../../lib/format";
import { getApiErrorMessage } from "../../lib/apiErrors";
import { getAccountLabel } from "../../lib/accountLabel";
import { getCachedBillingSnapshot, hasFreshBillingCache, loadBillingSnapshot } from "../../lib/appDataCache";

type PlanGroup = {
  key: "subscription" | "pack";
  label: string;
  description: string;
  plans: PlanResponse[];
};

type PurchaseSyncState = {
  status: "syncing" | "synced" | "delayed";
  orderLabel: string | null;
};

type RefundSyncState = {
  orderId: string;
  orderLabel: string | null;
  status: "syncing" | "synced" | "delayed";
};

const formatPrice = (amountCents: number, currency: string, billingInterval: string | null): string => {
  if (amountCents <= 0) {
    return "Free";
  }

  const amount = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase()
  }).format(amountCents / 100);

  return billingInterval ? `${amount}/${billingInterval}` : amount;
};

const describeSubscriptionStatus = (status: string | null): string => {
  if (!status) {
    return "No active subscription";
  }
  if (status === "active") {
    return "Active";
  }
  if (status === "canceled") {
    return "Cancels at period end";
  }
  if (status === "revoked") {
    return "Revoked";
  }
  return status.replaceAll("_", " ");
};

const getStatusTone = (status: string | null): string => {
  if (status === "active" || status === "paid" || status === "refunded") {
    return chrome.statusPillSuccess;
  }
  if (status === "refund_pending" || status === "canceled") {
    return chrome.statusPillWarning;
  }
  if (status === "revoked") {
    return chrome.statusPillDanger;
  }
  return chrome.statusPillMuted;
};

const getOrderLabel = (
  order:
    | Pick<BillingOrderHistoryEntry, "plan_name" | "plan_type">
    | Pick<PackBillingState, "plan_name">
    | null
    | undefined
): string | null => {
  if (!order) {
    return null;
  }

  if (order.plan_name) {
    return order.plan_name;
  }

  if ("plan_type" in order) {
    return order.plan_type === "subscription" ? "Subscription" : "Pack";
  }

  return "Pack";
};

const findRecentOrder = (
  orders: BillingOrderHistoryEntry[],
  checkoutStartedAt: number | null
): BillingOrderHistoryEntry | null => {
  if (!checkoutStartedAt) {
    return null;
  }

  const threshold = checkoutStartedAt - 120_000;

  return (
    [...orders]
      .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())
      .find((entry) => new Date(entry.created_at).getTime() >= threshold) ?? null
  );
};

function BillingPageContent() {
  const searchParams = useSearchParams();
  const { accessToken, loading: shellLoading, remainingSeconds, setRemainingSeconds, signOut, user } = useAppShell();
  const checkoutStatus = searchParams.get("checkout");
  const customerSessionToken = searchParams.get("customer_session_token");
  const cachedBillingSnapshot = getCachedBillingSnapshot();

  const [plans, setPlans] = useState<PlanResponse[]>(cachedBillingSnapshot?.plansData ?? []);
  const [usage, setUsage] = useState<UsageOverviewResponse | null>(cachedBillingSnapshot?.usageData ?? null);
  const [account, setAccount] = useState<BillingAccountResponse | null>(cachedBillingSnapshot?.accountData ?? null);

  const [loading, setLoading] = useState(() => cachedBillingSnapshot === null);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [refundLoading, setRefundLoading] = useState<string | null>(null);
  const [offerMode, setOfferMode] = useState<"subscription" | "pack">("subscription");

  const [purchaseSync, setPurchaseSync] = useState<PurchaseSyncState | null>(null);
  const [refundSync, setRefundSync] = useState<RefundSyncState | null>(null);
  const [syncRefreshLoading, setSyncRefreshLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const checkoutStartRef = useRef<number | null>(null);
  const refundPollRef = useRef<number | null>(null);

  const loadBilling = useCallback(
    async (showLoading: boolean) => {
      if (!accessToken) {
        return null;
      }

      if (showLoading) {
        setLoading(true);
      }

      try {
        const snapshot = await loadBillingSnapshot(accessToken);
        setPlans(snapshot.plansData);
        setUsage(snapshot.usageData);
        setAccount(snapshot.accountData);
        setRemainingSeconds(snapshot.usageData?.total_remaining_seconds ?? null);
        setError(null);
        return snapshot;
      } catch (err) {
        setError(getApiErrorMessage(err, "Unable to load billing details."));
        return null;
      } finally {
        if (showLoading) {
          setLoading(false);
        }
      }
    },
    [accessToken, setRemainingSeconds]
  );

  useEffect(() => {
    if (!accessToken) {
      return;
    }

    const cacheIsFresh = hasFreshBillingCache();
    if (cacheIsFresh) {
      const nextSnapshot = getCachedBillingSnapshot();
      setPlans(nextSnapshot?.plansData ?? []);
      setUsage(nextSnapshot?.usageData ?? null);
      setAccount(nextSnapshot?.accountData ?? null);
      setLoading(false);
      setError(null);
      return;
    }

    void loadBilling(cachedBillingSnapshot === null);
  }, [accessToken, cachedBillingSnapshot, loadBilling]);

  useEffect(() => {
    if (checkoutStatus !== "success") {
      return;
    }

    if (!checkoutStartRef.current) {
      checkoutStartRef.current = Date.now();
    }

    setPurchaseSync({
      status: "syncing",
      orderLabel: null
    });

    let attempts = 0;
    const maxAttempts = 20;
    const timer = window.setInterval(async () => {
      attempts += 1;
      const result = await loadBilling(false);
      const recentOrder = findRecentOrder(result?.accountData?.orders ?? [], checkoutStartRef.current);

      if (recentOrder) {
        setPurchaseSync({
          status: "synced",
          orderLabel: getOrderLabel(recentOrder)
        });
        window.clearInterval(timer);
        return;
      }

      if (attempts >= maxAttempts) {
        setPurchaseSync((current) => ({
          status: "delayed",
          orderLabel: current?.orderLabel ?? null
        }));
        window.clearInterval(timer);
      }
    }, 2500);

    return () => {
      window.clearInterval(timer);
    };
  }, [checkoutStatus, customerSessionToken, loadBilling]);

  useEffect(() => {
    return () => {
      if (refundPollRef.current !== null) {
        window.clearInterval(refundPollRef.current);
      }
    };
  }, []);

  const planGroups = useMemo<PlanGroup[]>(() => {
    const subscriptions = plans.filter((plan) => plan.plan_type === "subscription");
    const packs = plans.filter((plan) => plan.plan_type === "pack");

    return [
      {
        key: "subscription",
        label: "Monthly access",
        description: "Best for steady listening and recurring briefing volume.",
        plans: subscriptions
      },
      {
        key: "pack",
        label: "One-time packs",
        description: "Add reserve time when you need extra coverage without a recurring change.",
        plans: packs
      }
    ];
  }, [plans]);

  const activePackCount = useMemo(() => {
    return (account?.packs ?? []).filter((pack) => pack.remaining_seconds > 0 && pack.status !== "refunded").length;
  }, [account?.packs]);

  const canManageBilling = useMemo(() => {
    return (account?.orders ?? []).some((order) => order.paid_amount_cents > 0);
  }, [account?.orders]);

  const subscriptionStatusText = describeSubscriptionStatus(account?.subscription.status ?? null);

  const accessNote = useMemo(() => {
    if ((usage?.pack_remaining_seconds ?? 0) > 0 && usage?.pack_expires_at) {
      return `Pack reserve expires ${formatDate(usage.pack_expires_at)}.`;
    }

    const subscriptionPlanName = account?.subscription.plan_name ?? usage?.subscription_plan_name;
    const hasPaidPlan = Boolean(subscriptionPlanName && subscriptionPlanName.toLowerCase() !== "free");
    if (hasPaidPlan && account?.subscription.period_end) {
      return `Current plan renews ${formatDate(account.subscription.period_end)}.`;
    }

    return "Add more listening time whenever you need it.";
  }, [
    usage?.pack_remaining_seconds,
    usage?.pack_expires_at,
    usage?.subscription_plan_name,
    account?.subscription.plan_name,
    account?.subscription.period_end
  ]);

  const visiblePlanGroup = useMemo(() => {
    return planGroups.find((group) => group.key === offerMode) ?? null;
  }, [offerMode, planGroups]);

  const handleCheckout = async (planId: string) => {
    if (checkoutLoading) {
      return;
    }

    setCheckoutLoading(planId);
    setError(null);

    try {
      if (!accessToken) {
        return;
      }

      const api = createApiClient(accessToken);
      const { data, error: apiError } = await api.POST("/billing/checkout", {
        body: {
          plan_id: planId
        }
      });

      if (apiError) {
        setError(getApiErrorMessage(apiError, "Unable to start checkout."));
        return;
      }

      if (data?.checkout_url) {
        window.location.href = data.checkout_url;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setCheckoutLoading(null);
    }
  };

  const handlePortal = async () => {
    if (portalLoading) {
      return;
    }

    setPortalLoading(true);
    setError(null);

    try {
      if (!accessToken) {
        return;
      }

      const api = createApiClient(accessToken);
      const { data, error: apiError } = await api.POST("/billing/portal");

      if (apiError) {
        setError(getApiErrorMessage(apiError, "Unable to open billing portal."));
        return;
      }

      if (data?.portal_url) {
        window.location.href = data.portal_url;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setPortalLoading(false);
    }
  };

  const handleRefund = async (polarOrderId: string) => {
    if (refundLoading) {
      return;
    }

    setRefundLoading(polarOrderId);
    setError(null);

    try {
      if (!accessToken) {
        return;
      }

      const api = createApiClient(accessToken);
      const { error: apiError } = await api.POST("/billing/packs/{polar_order_id}/refund", {
        params: {
          path: {
            polar_order_id: polarOrderId
          }
        }
      });

      if (apiError) {
        setError(getApiErrorMessage(apiError, "Unable to request pack refund."));
        return;
      }

      setAccount((previous) => {
        if (!previous) {
          return previous;
        }

        return {
          ...previous,
          packs: previous.packs.map((pack) =>
            pack.polar_order_id === polarOrderId
              ? {
                  ...pack,
                  status: "refund_pending",
                  is_refundable: false,
                  refundable_amount_cents: 0
                }
              : pack
          ),
          orders: previous.orders.map((order) =>
            order.polar_order_id === polarOrderId
              ? {
                  ...order,
                  status: "refund_pending"
                }
              : order
          )
        };
      });

      const refundTargetOrder =
        account?.orders.find((order) => order.polar_order_id === polarOrderId) ??
        account?.packs.find((pack) => pack.polar_order_id === polarOrderId) ??
        null;

      setRefundSync({
        orderId: polarOrderId,
        orderLabel: getOrderLabel(refundTargetOrder),
        status: "syncing"
      });

      if (refundPollRef.current !== null) {
        window.clearInterval(refundPollRef.current);
      }

      let attempts = 0;
      const maxAttempts = 24;
      refundPollRef.current = window.setInterval(async () => {
        attempts += 1;
        const result = await loadBilling(false);
        const status =
          (result?.accountData?.orders ?? []).find((order) => order.polar_order_id === polarOrderId)?.status ?? null;

        if (status === "refunded") {
          if (refundPollRef.current !== null) {
            window.clearInterval(refundPollRef.current);
            refundPollRef.current = null;
          }
          setRefundSync((current) =>
            current
              ? {
                  ...current,
                  status: "synced"
                }
              : null
          );
          return;
        }

        if (attempts >= maxAttempts) {
          if (refundPollRef.current !== null) {
            window.clearInterval(refundPollRef.current);
            refundPollRef.current = null;
          }
          setRefundSync((current) =>
            current
              ? {
                  ...current,
                  status: "delayed"
                }
              : null
          );
        }
      }, 2500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setRefundLoading(null);
    }
  };

  const renderRefundAction = (pack: PackBillingState) => {
    if (pack.status === "refund_pending") {
      return <span className={chrome.statusPillWarning}>Refund pending</span>;
    }

    if (pack.status === "refunded") {
      return <span className={chrome.statusPillSuccess}>Refunded</span>;
    }

    if (!pack.is_refundable) {
      return <span className={chrome.statusPillMuted}>Unavailable</span>;
    }

    return (
      <button
        className={chrome.secondaryButton}
        type="button"
        onClick={() => handleRefund(pack.polar_order_id)}
        disabled={refundLoading === pack.polar_order_id}
      >
        {refundLoading === pack.polar_order_id
          ? "Requesting refund..."
          : `Refund ${formatPrice(pack.refundable_amount_cents, pack.currency, null)}`}
      </button>
    );
  };

  const handleRefreshSyncStatus = useCallback(async () => {
    if (syncRefreshLoading) {
      return;
    }

    setSyncRefreshLoading(true);
    try {
      const result = await loadBilling(false);
      const orders = result?.accountData?.orders ?? [];

      if (purchaseSync) {
        const recentOrder = findRecentOrder(orders, checkoutStartRef.current);
        if (recentOrder) {
          setPurchaseSync({
            status: "synced",
            orderLabel: getOrderLabel(recentOrder)
          });
        }
      }

      if (refundSync) {
        const matchingOrder = orders.find((order) => order.polar_order_id === refundSync.orderId) ?? null;
        if (matchingOrder?.status === "refunded") {
          setRefundSync({
            ...refundSync,
            orderLabel: refundSync.orderLabel ?? getOrderLabel(matchingOrder),
            status: "synced"
          });
        }
      }
    } finally {
      setSyncRefreshLoading(false);
    }
  }, [loadBilling, purchaseSync, refundSync, syncRefreshLoading]);

  if (loading) {
    return (
      <div className={chrome.pageFrame}>
        <AppShellHeader active="billing" remainingSeconds={null} accountLabel={null} onSignOut={() => undefined} />
        <main className={chrome.mainFrame}>
          <section className={chrome.surface}>
            <h1 className={chrome.surfaceTitle}>Loading your access...</h1>
            <p className={chrome.surfaceText}>Fetching plans, balances, and billing details.</p>
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader
        active="billing"
        remainingSeconds={remainingSeconds}
        accountLabel={getAccountLabel(user)}
        onSignOut={signOut}
      />

      <main className={chrome.mainFrame}>
        <section className={`${chrome.heroBlock} ${styles.pageColumn}`}>
          <div>
            <p className={chrome.heroEyebrow}>Billing</p>
            <h1 className={chrome.heroTitle}>Your access</h1>
            <p className={chrome.heroText}>See what listening time you have now, then add more when you need it.</p>
          </div>
          <div className={chrome.heroActions}>
            {canManageBilling ? (
              <button className={chrome.primaryButton} type="button" onClick={handlePortal} disabled={portalLoading || shellLoading}>
                {portalLoading ? "Opening portal..." : "Manage plan"}
              </button>
            ) : (
              <a className={chrome.primaryButton} href="#billing-offers">
                Get more listening time
              </a>
            )}
            <Link className={chrome.secondaryButton} href="/app">
              Back to workspace
            </Link>
          </div>
        </section>

        {purchaseSync ? (
          <section
            className={`${chrome.notice} ${styles.pageColumn} ${
              purchaseSync.status === "delayed" ? chrome.noticeWarning : chrome.noticeInfo
            }`}
          >
            <h2 className={chrome.noticeTitle}>Purchase status</h2>
            <p className={chrome.noticeText}>
              {purchaseSync.status === "syncing"
                ? "Payment received. We are updating your listening balance now."
                : purchaseSync.status === "synced"
                  ? `${purchaseSync.orderLabel ?? "Your purchase"} is confirmed and your access is updated below.`
                  : "Payment succeeded, but provider confirmation is taking longer than expected. You do not need to pay again."}
            </p>
            {purchaseSync.status === "delayed" ? (
              <div className={chrome.actionRow}>
                <button
                  className={chrome.secondaryButton}
                  type="button"
                  onClick={() => void handleRefreshSyncStatus()}
                  disabled={syncRefreshLoading}
                >
                  {syncRefreshLoading ? "Refreshing status..." : "Refresh status"}
                </button>
              </div>
            ) : null}
          </section>
        ) : null}

        {refundSync ? (
          <section
            className={`${chrome.notice} ${styles.pageColumn} ${
              refundSync.status === "delayed" ? chrome.noticeWarning : chrome.noticeInfo
            }`}
          >
            <h2 className={chrome.noticeTitle}>Refund status</h2>
            <p className={chrome.noticeText}>
              {refundSync.status === "syncing"
                ? `Refund requested for ${refundSync.orderLabel ?? "this pack"}. Waiting for provider confirmation now.`
                : refundSync.status === "synced"
                  ? `${refundSync.orderLabel ?? "This pack"} is now marked refunded.`
                  : "The refund request was accepted, but confirmation is still arriving from the provider. You do not need to submit it again."}
            </p>
            {refundSync.status === "delayed" ? (
              <div className={chrome.actionRow}>
                <button
                  className={chrome.secondaryButton}
                  type="button"
                  onClick={() => void handleRefreshSyncStatus()}
                  disabled={syncRefreshLoading}
                >
                  {syncRefreshLoading ? "Refreshing status..." : "Refresh status"}
                </button>
              </div>
            ) : null}
          </section>
        ) : null}

        {error ? (
          <section className={`${chrome.notice} ${styles.pageColumn} ${chrome.noticeError}`}>
            <h2 className={chrome.noticeTitle}>Billing action failed</h2>
            <p className={chrome.noticeText}>{error}</p>
          </section>
        ) : null}

        <section className={`${chrome.surface} ${styles.pageColumn} ${styles.accessSection}`}>
          <div className={chrome.surfaceHeader}>
            <div>
              <h2 className={chrome.surfaceTitle}>Current access</h2>
              <p className={chrome.surfaceText}>What you have now, with room to add more only when you need it.</p>
            </div>
            <span className={getStatusTone(account?.subscription.status ?? null)}>{subscriptionStatusText}</span>
          </div>

          <div className={styles.accessSummary}>
            <article className={styles.accessStat}>
              <p className={styles.accessLabel}>Available time</p>
              <p className={styles.accessValue}>{usage ? formatDuration(usage.total_remaining_seconds) : "-"}</p>
            </article>
            <article className={styles.accessStat}>
              <p className={styles.accessLabel}>Current plan</p>
              <p className={styles.accessValue}>{account?.subscription.plan_name ?? usage?.subscription_plan_name ?? "Free"}</p>
              <p className={styles.accessHint}>{subscriptionStatusText}</p>
            </article>
            <article className={styles.accessStat}>
              <p className={styles.accessLabel}>Pack reserve</p>
              <p className={styles.accessValue}>{formatDuration(usage?.pack_remaining_seconds ?? 0)}</p>
              <p className={styles.accessHint}>
                {(usage?.pack_remaining_seconds ?? 0) > 0 ? `Expires ${formatDate(usage?.pack_expires_at ?? null)}` : "Add packs anytime"}
              </p>
            </article>
          </div>

          <p className={styles.accessNote}>{accessNote}</p>
        </section>

        <section className={`${chrome.surface} ${styles.pageColumn} ${styles.offerSection}`} id="billing-offers">
          <div className={chrome.surfaceHeader}>
            <div>
              <h2 className={chrome.surfaceTitle}>Get more listening time</h2>
              <p className={chrome.surfaceText}>Choose monthly access or add a one-time reserve when your listening expands.</p>
            </div>
          </div>

          <div className={styles.offerSwitch}>
            <button
              className={`${styles.offerSwitchButton} ${offerMode === "subscription" ? styles.offerSwitchButtonActive : ""}`}
              type="button"
              onClick={() => setOfferMode("subscription")}
            >
              Monthly access
            </button>
            <button
              className={`${styles.offerSwitchButton} ${offerMode === "pack" ? styles.offerSwitchButtonActive : ""}`}
              type="button"
              onClick={() => setOfferMode("pack")}
            >
              One-time packs
            </button>
          </div>

          {visiblePlanGroup ? <p className={styles.offerIntro}>{visiblePlanGroup.description}</p> : null}

          {visiblePlanGroup ? (
            <div className={styles.planGrid}>
              {visiblePlanGroup.plans.map((plan) => {
                const isCurrentSubscription =
                  visiblePlanGroup.key === "subscription" &&
                  account?.subscription.status === "active" &&
                  account.subscription.plan_name === plan.name;

                return (
                  <article className={styles.planCard} key={plan.plan_id}>
                    <div className={styles.planCardBody}>
                      <div>
                        <p className={styles.planName}>{plan.name}</p>
                        <p className={styles.planPrice}>{formatPrice(plan.amount_cents, plan.currency, plan.billing_interval)}</p>
                      </div>
                      <div className={styles.planMeta}>
                        <p className={chrome.subtleText}>{formatDuration(plan.quota_seconds ?? 0)} included</p>
                        {visiblePlanGroup.key === "pack" && plan.pack_expiry_days ? (
                          <p className={chrome.subtleText}>Expires in {plan.pack_expiry_days} days</p>
                        ) : null}
                      </div>
                    </div>
                    <button
                      className={isCurrentSubscription ? chrome.ghostButton : chrome.primaryButton}
                      type="button"
                      onClick={() => handleCheckout(plan.plan_id)}
                      disabled={checkoutLoading === plan.plan_id || isCurrentSubscription}
                    >
                      {checkoutLoading === plan.plan_id
                        ? "Opening checkout..."
                        : isCurrentSubscription
                          ? "Current plan"
                          : visiblePlanGroup.key === "subscription"
                            ? "Upgrade now"
                            : "Buy pack"}
                    </button>
                  </article>
                );
              })}
            </div>
          ) : null}
        </section>

        <section className={`${chrome.surface} ${styles.pageColumn} ${styles.detailsSection}`}>
          <div className={chrome.surfaceHeader}>
            <div>
              <h2 className={chrome.surfaceTitle}>Details</h2>
              <p className={chrome.surfaceText}>Only the payment details worth keeping close.</p>
            </div>
          </div>

          <div className={styles.detailsStack}>
            <details className={styles.detailDisclosure} open={activePackCount > 0}>
              <summary className={styles.detailSummary}>
                <span>Purchased packs</span>
                <span className={styles.detailCount}>{account?.packs.length ?? 0}</span>
              </summary>

              {!account || account.packs.length === 0 ? (
                <p className={chrome.emptyState}>No packs purchased yet.</p>
              ) : (
                <div className={chrome.list}>
                  {account.packs.map((pack) => (
                    <article className={chrome.listRow} key={pack.polar_order_id}>
                      <div className={chrome.listPrimary}>
                        <p className={chrome.listTitle}>{pack.plan_name ?? "Pack"}</p>
                        <p className={chrome.listMeta}>
                          {formatDuration(pack.remaining_seconds)} left · Expires {formatDate(pack.expires_at)}
                        </p>
                        <p className={chrome.listMeta}>
                          Used {formatDuration(pack.consumed_seconds)} / {formatDuration(pack.granted_seconds)}
                        </p>
                      </div>
                      <div className={styles.packActions}>{renderRefundAction(pack)}</div>
                    </article>
                  ))}
                </div>
              )}
            </details>

            <details className={styles.detailDisclosure}>
              <summary className={styles.detailSummary}>
                <span>Billing history</span>
                <span className={styles.detailCount}>{account?.orders.length ?? 0}</span>
              </summary>

              {!account || account.orders.length === 0 ? (
                <p className={chrome.emptyState}>No billing events yet.</p>
              ) : (
                <div className={chrome.list}>
                  {account.orders.slice(0, 12).map((entry: BillingOrderHistoryEntry) => (
                    <article className={chrome.listRow} key={entry.polar_order_id}>
                      <div className={chrome.listPrimary}>
                        <p className={chrome.listTitle}>{entry.plan_name ?? entry.plan_type}</p>
                        <p className={chrome.listMeta}>{formatDate(entry.created_at)}</p>
                      </div>
                      <div className={chrome.listAside}>
                        <span className={getStatusTone(entry.status)}>{entry.status.replaceAll("_", " ")}</span>
                        <span>
                          Paid {formatPrice(entry.paid_amount_cents, entry.currency, null)}
                          {entry.refunded_amount_cents > 0
                            ? ` · Refunded ${formatPrice(entry.refunded_amount_cents, entry.currency, null)}`
                            : ""}
                        </span>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </details>
          </div>
        </section>
      </main>
    </div>
  );
}

export default function BillingPage() {
  return (
    <Suspense
      fallback={
        <div className={chrome.pageFrame}>
          <AppShellHeader active="billing" remainingSeconds={null} accountLabel={null} onSignOut={() => undefined} />
          <main className={chrome.mainFrame}>
            <section className={chrome.surface}>
              <h1 className={chrome.surfaceTitle}>Loading your access...</h1>
              <p className={chrome.surfaceText}>Preparing your plan and billing details.</p>
            </section>
          </main>
        </div>
      }
    >
      <BillingPageContent />
    </Suspense>
  );
}

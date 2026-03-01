"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import type {
  BillingAccountResponse,
  BillingOrderHistoryEntry,
  PackBillingState,
  PlanResponse,
  UsageOverviewResponse
} from "@fathom/api-client";
import { createApiClient } from "@fathom/api-client";

import styles from "../app.module.css";
import { formatDate, formatDuration } from "../../lib/format";
import { getSupabaseClient } from "../../lib/supabaseClient";
import { getApiErrorMessage } from "../../lib/apiErrors";

type PlanGroup = {
  label: string;
  plans: PlanResponse[];
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

export default function BillingPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const checkoutStatus = searchParams.get("checkout");
  const customerSessionToken = searchParams.get("customer_session_token");
  const [plans, setPlans] = useState<PlanResponse[]>([]);
  const [usage, setUsage] = useState<UsageOverviewResponse | null>(null);
  const [account, setAccount] = useState<BillingAccountResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [refundLoading, setRefundLoading] = useState<string | null>(null);
  const [refundSyncOrderId, setRefundSyncOrderId] = useState<string | null>(null);
  const [refundSyncStatus, setRefundSyncStatus] = useState<"syncing" | "delayed" | null>(null);
  const [syncStatus, setSyncStatus] = useState<"syncing" | "synced" | "delayed" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const checkoutStartRef = useRef<number | null>(null);
  const refundPollRef = useRef<number | null>(null);

  const loadBilling = useCallback(
    async (showLoading: boolean): Promise<{
      plansData: PlanResponse[];
      usageData: UsageOverviewResponse | null;
      accountData: BillingAccountResponse | null;
    } | null> => {
      if (showLoading) {
        setLoading(true);
      }
      try {
        const supabase = getSupabaseClient();
        const { data: sessionData } = await supabase.auth.getSession();
        if (!sessionData.session) {
          router.replace("/signin");
          return null;
        }

        const api = createApiClient(sessionData.session.access_token);
        const [
          { data: plansData, error: plansError },
          { data: usageData, error: usageError },
          { data: accountData, error: accountError }
        ] = await Promise.all([
          api.GET("/billing/plans"),
          api.GET("/billing/usage"),
          api.GET("/billing/account")
        ]);

        if (plansError) {
          setError(getApiErrorMessage(plansError, "Unable to load plans."));
          return null;
        }
        if (usageError) {
          setError(getApiErrorMessage(usageError, "Unable to load usage."));
          return null;
        }
        if (accountError) {
          setError(getApiErrorMessage(accountError, "Unable to load billing account."));
          return null;
        }

        const normalizedPlans = plansData ?? [];
        const normalizedUsage = usageData ?? null;
        const normalizedAccount = accountData ?? null;

        setPlans(normalizedPlans);
        setUsage(normalizedUsage);
        setAccount(normalizedAccount);
        return {
          plansData: normalizedPlans,
          usageData: normalizedUsage,
          accountData: normalizedAccount
        };
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
        return null;
      } finally {
        if (showLoading) {
          setLoading(false);
        }
      }
    },
    [router]
  );

  useEffect(() => {
    void loadBilling(true);
  }, [loadBilling]);

  useEffect(() => {
    if (checkoutStatus !== "success") {
      return;
    }
    if (!checkoutStartRef.current) {
      checkoutStartRef.current = Date.now();
    }
    setSyncStatus("syncing");

    let attempts = 0;
    const maxAttempts = 20;
    const timer = setInterval(async () => {
      attempts += 1;
      const result = await loadBilling(false);
      const recentOrderFound = (result?.accountData?.orders ?? []).some((entry) => {
        const createdAt = new Date(entry.created_at).getTime();
        return createdAt >= (checkoutStartRef.current ?? 0) - 120_000;
      });
      if (recentOrderFound) {
        setSyncStatus("synced");
        clearInterval(timer);
        return;
      }
      if (attempts >= maxAttempts) {
        setSyncStatus("delayed");
        clearInterval(timer);
      }
    }, 2500);

    return () => {
      clearInterval(timer);
    };
  }, [checkoutStatus, customerSessionToken, loadBilling]);

  useEffect(() => {
    return () => {
      if (refundPollRef.current !== null) {
        window.clearInterval(refundPollRef.current);
      }
    };
  }, []);

  const groupedPlans = useMemo<PlanGroup[]>(() => {
    const subscriptions = plans.filter((plan) => plan.plan_type === "subscription");
    const packs = plans.filter((plan) => plan.plan_type === "pack");
    return [
      { label: "Subscriptions", plans: subscriptions },
      { label: "Packs (no commitment)", plans: packs }
    ];
  }, [plans]);

  const handleCheckout = async (planId: string) => {
    if (checkoutLoading) {
      return;
    }
    setCheckoutLoading(planId);
    setError(null);

    try {
      const supabase = getSupabaseClient();
      const { data: sessionData } = await supabase.auth.getSession();
      if (!sessionData.session) {
        router.replace("/signin");
        return;
      }

      const api = createApiClient(sessionData.session.access_token);
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
      const supabase = getSupabaseClient();
      const { data: sessionData } = await supabase.auth.getSession();
      if (!sessionData.session) {
        router.replace("/signin");
        return;
      }

      const api = createApiClient(sessionData.session.access_token);
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
      const supabase = getSupabaseClient();
      const { data: sessionData } = await supabase.auth.getSession();
      if (!sessionData.session) {
        router.replace("/signin");
        return;
      }

      const api = createApiClient(sessionData.session.access_token);
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
      setRefundSyncOrderId(polarOrderId);
      setRefundSyncStatus("syncing");

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
          setRefundSyncOrderId(null);
          setRefundSyncStatus(null);
          return;
        }
        if (attempts >= maxAttempts) {
          if (refundPollRef.current !== null) {
            window.clearInterval(refundPollRef.current);
            refundPollRef.current = null;
          }
          setRefundSyncStatus("delayed");
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
      return <p className={styles.cardText}>Refund pending confirmation</p>;
    }
    if (pack.status === "refunded") {
      return <p className={styles.cardText}>Refund completed</p>;
    }
    if (!pack.is_refundable) {
      return <p className={styles.cardText}>Refund unavailable</p>;
    }

    return (
      <button
        className={styles.secondaryButton}
        type="button"
        onClick={() => handleRefund(pack.polar_order_id)}
        disabled={refundLoading === pack.polar_order_id}
      >
        {refundLoading === pack.polar_order_id
          ? "Requesting refund…"
          : `Refund ${formatPrice(pack.refundable_amount_cents, pack.currency, null)}`}
      </button>
    );
  };

  const subscriptionStatusText = useMemo(() => {
    const status = account?.subscription.status ?? null;
    if (!status) {
      return "No active subscription";
    }
    if (status === "canceled") {
      return "Cancels at period end";
    }
    if (status === "active") {
      return "Active";
    }
    return status.replaceAll("_", " ");
  }, [account?.subscription.status, usage?.subscription_plan_name]);

  if (loading) {
    return (
      <div className={styles.page}>
        <header className={styles.header}>
          <div className={styles.brand}>
            <span className={styles.brandMark} aria-hidden="true" />
            Fathom
          </div>
        </header>
        <main className={styles.main}>
          <div className={styles.card}>
            <h1 className={styles.cardTitle}>Loading billing…</h1>
            <p className={styles.cardText}>Fetching your plans and usage.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true" />
          Fathom
        </div>
        <div className={styles.headerActions}>
          <button className={styles.secondaryButton} type="button" onClick={handlePortal} disabled={portalLoading}>
            {portalLoading ? "Opening portal…" : "Manage billing"}
          </button>
          <Link className={styles.button} href="/app">
            Back to app
          </Link>
        </div>
      </header>

      <main className={styles.main}>
        <section className={styles.card}>
          <div className={styles.sectionHeader}>
            <div>
              <h1 className={styles.cardTitle}>Usage overview</h1>
              <p className={styles.cardText}>Track remaining time and renew before you run out.</p>
            </div>
            <div className={styles.usageSummary}>
              <div className={styles.usageValue}>
                {usage ? formatDuration(usage.total_remaining_seconds) : "—"}
              </div>
              <div className={styles.usageLabel}>Total remaining</div>
            </div>
          </div>

          {usage ? (
            <div className={styles.usageGrid}>
              <div className={styles.usageCard}>
                <p className={styles.usageLabel}>Subscription</p>
                <p className={styles.usageValue}>{formatDuration(usage.subscription_remaining_seconds)}</p>
                <p className={styles.cardText}>
                  Plan: {usage.subscription_plan_name ?? "Free"}
                </p>
              </div>
              <div className={styles.usageCard}>
                <p className={styles.usageLabel}>Pack credits</p>
                <p className={styles.usageValue}>{formatDuration(usage.pack_remaining_seconds)}</p>
                <p className={styles.cardText}>Expires: {formatDate(usage.pack_expires_at)}</p>
              </div>
              <div className={styles.usageCard}>
                <p className={styles.usageLabel}>Debt / Status</p>
                <p className={styles.usageValue}>{formatDuration(usage.debt_seconds)}</p>
                <p className={styles.cardText}>{usage.is_blocked ? "Blocked until top-up" : "Account active"}</p>
              </div>
            </div>
          ) : null}
        </section>

        {syncStatus ? (
          <section className={styles.card}>
            <h2 className={styles.cardTitle}>Checkout status</h2>
            <p className={styles.cardText}>
              {syncStatus === "syncing"
                ? "Payment received. Syncing credits and billing records..."
                : syncStatus === "synced"
                  ? "Billing synced. Your new purchase is now visible."
                  : "Payment was received, but syncing is delayed. Refresh shortly or open billing portal."}
            </p>
          </section>
        ) : null}

        {refundSyncOrderId && refundSyncStatus ? (
          <section className={styles.card}>
            <h2 className={styles.cardTitle}>Refund status</h2>
            <p className={styles.cardText}>
              {refundSyncStatus === "syncing"
                ? "Refund request sent. Waiting for Polar confirmation..."
                : "Refund is still processing. This can take a few minutes; no action needed."}
            </p>
          </section>
        ) : null}

        <section className={styles.card}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.cardTitle}>Current billing</h2>
              <p className={styles.cardText}>See exactly what is active before purchasing more.</p>
            </div>
          </div>

          <div className={styles.usageGrid}>
            <div className={styles.usageCard}>
              <p className={styles.usageLabel}>Subscription status</p>
              <p className={styles.usageValue}>{subscriptionStatusText}</p>
              <p className={styles.cardText}>Plan: {account?.subscription.plan_name ?? usage?.subscription_plan_name ?? "Free"}</p>
              <p className={styles.cardText}>Period ends: {formatDate(account?.subscription.period_end ?? null)}</p>
            </div>
            <div className={styles.usageCard}>
              <p className={styles.usageLabel}>Active packs</p>
              <p className={styles.usageValue}>{account?.packs.length ?? 0}</p>
              <p className={styles.cardText}>Remaining pack credits: {formatDuration(usage?.pack_remaining_seconds ?? 0)}</p>
              <p className={styles.cardText}>Next expiry: {formatDate(usage?.pack_expires_at ?? null)}</p>
            </div>
          </div>
        </section>

        <section className={styles.card}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.cardTitle}>Your packs</h2>
              <p className={styles.cardText}>Refunds are one-time per pack order and based on unused credits.</p>
            </div>
          </div>
          {!account || account.packs.length === 0 ? (
            <p className={styles.cardText}>No packs purchased yet.</p>
          ) : (
            <div className={styles.planGrid}>
              {account.packs.map((pack) => (
                <div className={styles.planCard} key={pack.polar_order_id}>
                  <div>
                    <h3 className={styles.planTitle}>{pack.plan_name ?? "Pack"}</h3>
                    <p className={styles.cardText}>Status: {pack.status.replaceAll("_", " ")}</p>
                    <p className={styles.cardText}>
                      Used {formatDuration(pack.consumed_seconds)} / {formatDuration(pack.granted_seconds)}
                    </p>
                    <p className={styles.cardText}>Remaining: {formatDuration(pack.remaining_seconds)}</p>
                    <p className={styles.cardText}>Expires: {formatDate(pack.expires_at)}</p>
                  </div>
                  {renderRefundAction(pack)}
                </div>
              ))}
            </div>
          )}
        </section>

        <section className={styles.card}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.cardTitle}>Billing history</h2>
              <p className={styles.cardText}>Recent payments and refunds.</p>
            </div>
          </div>
          {!account || account.orders.length === 0 ? (
            <p className={styles.cardText}>No billing events yet.</p>
          ) : (
            <div className={styles.historyList}>
              {account.orders.slice(0, 12).map((entry: BillingOrderHistoryEntry) => (
                <div className={styles.historyRow} key={entry.polar_order_id}>
                  <div>
                    <p className={styles.historyTitle}>{entry.plan_name ?? entry.plan_type}</p>
                    <p className={styles.cardText}>Order: {entry.polar_order_id}</p>
                  </div>
                  <div className={styles.historyMeta}>
                    <span>{entry.status.replaceAll("_", " ")}</span>
                    <span>
                      Paid {formatPrice(entry.paid_amount_cents, entry.currency, null)}
                      {entry.refunded_amount_cents > 0
                        ? ` • Refunded ${formatPrice(entry.refunded_amount_cents, entry.currency, null)}`
                        : ""}
                    </span>
                    <span>{formatDate(entry.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {groupedPlans.map((group) => (
          <section className={styles.card} key={group.label}>
            <div className={styles.sectionHeader}>
              <div>
                <h2 className={styles.cardTitle}>{group.label}</h2>
                <p className={styles.cardText}>
                  {group.label.includes("Packs")
                    ? "One‑time credits with a 6‑month expiry. Top up anytime."
                    : "Monthly credits with rollover up to 2x your limit."}
                </p>
              </div>
            </div>
            <div className={styles.planGrid}>
              {group.plans.map((plan) => (
                <div className={styles.planCard} key={plan.plan_id}>
                  <div>
                    <h3 className={styles.planTitle}>{plan.name}</h3>
                    <p className={styles.cardText}>{formatPrice(plan.amount_cents, plan.currency, plan.billing_interval)}</p>
                    <p className={styles.cardText}>
                      {formatDuration(plan.quota_seconds ?? 0)} included
                    </p>
                  </div>
                  <button
                    className={styles.secondaryButton}
                    type="button"
                    onClick={() => handleCheckout(plan.plan_id)}
                    disabled={checkoutLoading === plan.plan_id}
                  >
                    {checkoutLoading === plan.plan_id ? "Opening Polar…" : "Choose"}
                  </button>
                </div>
              ))}
            </div>
          </section>
        ))}

        {error ? <p className={styles.status}>{error}</p> : null}
      </main>
    </div>
  );
}

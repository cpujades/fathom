"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { PlanResponse, UsageOverviewResponse } from "@fathom/api-client";
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
  const [plans, setPlans] = useState<PlanResponse[]>([]);
  const [usage, setUsage] = useState<UsageOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadBilling = async () => {
      try {
        const supabase = getSupabaseClient();
        const { data: sessionData } = await supabase.auth.getSession();
        if (!sessionData.session) {
          router.replace("/signin");
          return;
        }

        const api = createApiClient(sessionData.session.access_token);
        const [{ data: plansData, error: plansError }, { data: usageData, error: usageError }] = await Promise.all([
          api.GET("/billing/plans"),
          api.GET("/billing/usage")
        ]);

        if (plansError) {
          setError(getApiErrorMessage(plansError, "Unable to load plans."));
          return;
        }
        if (usageError) {
          setError(getApiErrorMessage(usageError, "Unable to load usage."));
          return;
        }

        setPlans(plansData ?? []);
        setUsage(usageData ?? null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      } finally {
        setLoading(false);
      }
    };

    void loadBilling();
  }, [router]);

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

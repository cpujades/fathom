"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { BillingAccountResponse, UsageHistoryEntry, UsageOverviewResponse } from "@fathom/api-client";
import type { User } from "@supabase/supabase-js";
import { createApiClient } from "@fathom/api-client";

import { AppShellHeader } from "../components/AppShellHeader";
import { formatDate, formatDuration } from "../lib/format";
import { getApiErrorMessage } from "../lib/apiErrors";
import { getSupabaseClient } from "../lib/supabaseClient";
import styles from "./home.module.css";

const getAccountLabel = (user: User | null): string | null => {
  if (!user) {
    return null;
  }
  const fullName = (user.user_metadata?.full_name as string | undefined) ?? (user.user_metadata?.name as string | undefined);
  if (fullName && fullName.trim().length > 0) {
    return fullName.trim();
  }
  const email = user.email ?? null;
  if (!email) {
    return null;
  }
  const localPart = email.split("@")[0];
  return localPart || email;
};

export default function AppHome() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [usage, setUsage] = useState<UsageOverviewResponse | null>(null);
  const [account, setAccount] = useState<BillingAccountResponse | null>(null);
  const [recentUsage, setRecentUsage] = useState<UsageHistoryEntry[]>([]);

  useEffect(() => {
    let unsubscribe: (() => void) | null = null;

    const loadSession = async () => {
      try {
        router.prefetch("/app/jobs/new");
        const supabase = getSupabaseClient();
        const { data: sessionData, error: sessionError } = await supabase.auth.getSession();

        if (sessionError) {
          setError(sessionError.message);
        }

        if (!sessionData.session) {
          router.replace("/signin");
          return;
        }

        setUser(sessionData.session.user);

        const api = createApiClient(sessionData.session.access_token);
        const [
          { data: usageData, error: usageError },
          { data: accountData, error: accountError },
          { data: historyData, error: historyError }
        ] = await Promise.all([api.GET("/billing/usage"), api.GET("/billing/account"), api.GET("/billing/history")]);

        if (usageError) {
          setError(getApiErrorMessage(usageError, "Unable to load usage."));
        } else {
          setUsage(usageData ?? null);
        }

        if (accountError) {
          setError(getApiErrorMessage(accountError, "Unable to load billing state."));
        } else {
          setAccount(accountData ?? null);
        }

        if (historyError) {
          setError(getApiErrorMessage(historyError, "Unable to load recent activity."));
        } else {
          setRecentUsage((historyData ?? []).slice(0, 4));
        }

        const { data: authListener } = supabase.auth.onAuthStateChange((_event, authSession) => {
          if (!authSession) {
            router.replace("/signin");
          } else {
            setUser(authSession.user);
          }
        });

        unsubscribe = () => authListener.subscription.unsubscribe();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      } finally {
        setLoading(false);
      }
    };

    void loadSession();

    return () => {
      unsubscribe?.();
    };
  }, [router]);

  const handleSignOut = async () => {
    const supabase = getSupabaseClient();
    await supabase.auth.signOut();
    router.replace("/signin");
  };

  const handleSubmit = () => {
    if (submitting) {
      return;
    }

    if (!url.trim()) {
      setError("Please paste a valid podcast or YouTube URL.");
      return;
    }

    setError(null);
    setSubmitting(true);

    const trimmedUrl = url.trim();
    router.push(`/app/jobs/new?url=${encodeURIComponent(trimmedUrl)}`);
  };

  const subscriptionStatus = (() => {
    const status = account?.subscription.status;
    if (!status) {
      return "Free";
    }
    if (status === "active") {
      return "Active";
    }
    if (status === "canceled") {
      return "Cancels at period end";
    }
    return status.replaceAll("_", " ");
  })();

  return (
    <div className={styles.page}>
      <AppShellHeader
        active="home"
        remainingSeconds={usage?.total_remaining_seconds ?? null}
        accountLabel={getAccountLabel(user)}
        onSignOut={handleSignOut}
      />

      <main className={styles.main}>
        <section className={styles.commandGrid}>
          <article className={styles.card}>
            <h1 className={styles.commandTitle}>{loading ? "Loading workspace..." : "Start a briefing"}</h1>
            <p className={styles.commandText}>
              Paste a podcast or YouTube URL and Talven will generate a transcript and structured briefing.
            </p>

            <div className={styles.inputRow}>
              <input
                className={styles.input}
                type="url"
                placeholder="https://www.youtube.com/watch?v=..."
                aria-label="Podcast or YouTube URL"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                disabled={loading}
              />
              <button className={styles.primaryButton} type="button" onClick={handleSubmit} disabled={loading || submitting}>
                {submitting ? "Starting..." : "Generate briefing"}
              </button>
            </div>

            <p className={styles.inputHelp}>One input, one clear output: transcript, briefing, and optional PDF export.</p>
            {error ? <p className={styles.inlineStatus}>{error}</p> : null}
          </article>

          <aside className={styles.card}>
            <h2 className={styles.stateHeader}>Current state</h2>
            <div className={styles.stateGrid}>
              <article className={styles.stateTile}>
                <p className={styles.stateLabel}>Total remaining</p>
                <p className={styles.stateValue}>{formatDuration(usage?.total_remaining_seconds ?? 0)}</p>
              </article>
              <article className={styles.stateTile}>
                <p className={styles.stateLabel}>Subscription</p>
                <p className={styles.stateValue}>{account?.subscription.plan_name ?? usage?.subscription_plan_name ?? "Free"}</p>
                <p className={styles.stateHint}>{subscriptionStatus}</p>
              </article>
              <article className={styles.stateTile}>
                <p className={styles.stateLabel}>Pack balance</p>
                <p className={styles.stateValue}>{formatDuration(usage?.pack_remaining_seconds ?? 0)}</p>
                <p className={styles.stateHint}>Expires {formatDate(usage?.pack_expires_at ?? null)}</p>
              </article>
            </div>

            <div className={styles.quickLinks}>
              <Link className={styles.linkButton} href="/app/billing">
                Top up credits
              </Link>
            </div>
          </aside>
        </section>

        <section className={styles.card}>
          <h2 className={styles.recentTitle}>Recent activity</h2>
          <p className={styles.recentText}>Quick snapshot of your latest credit consumption events.</p>

          {loading ? (
            <p className={styles.emptyState}>Loading recent activity...</p>
          ) : recentUsage.length === 0 ? (
            <p className={styles.emptyState}>No activity yet. Start your first briefing above.</p>
          ) : (
            <div className={styles.list}>
              {recentUsage.map((entry, index) => (
                <article className={styles.row} key={`${entry.job_id ?? "job"}-${index}`}>
                  <div>
                    <p className={styles.rowTitle}>
                      {entry.source === "subscription" ? "Subscription usage" : "Pack usage"}
                    </p>
                    <p className={styles.rowMeta}>Job: {entry.job_id ?? "-"}</p>
                  </div>
                  <div className={styles.rowRight}>
                    <span>{formatDuration(entry.seconds_used)}</span>
                    <span>{formatDate(entry.created_at)}</span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

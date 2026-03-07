"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { UsageHistoryEntry } from "@fathom/api-client";
import { createApiClient } from "@fathom/api-client";

import { AppShellHeader } from "../../components/AppShellHeader";
import styles from "../app.module.css";
import { formatDate, formatDuration } from "../../lib/format";
import { getSupabaseClient } from "../../lib/supabaseClient";
import { getApiErrorMessage } from "../../lib/apiErrors";

const getAccountLabel = (fullName: string | null, email: string | null): string | null => {
  if (fullName && fullName.trim().length > 0) {
    return fullName.trim();
  }
  if (!email) {
    return null;
  }
  const localPart = email.split("@")[0];
  return localPart || email;
};

export default function HistoryPage() {
  const router = useRouter();
  const [history, setHistory] = useState<UsageHistoryEntry[]>([]);
  const [usageRemaining, setUsageRemaining] = useState<number | null>(null);
  const [accountLabel, setAccountLabel] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadHistory = async () => {
      try {
        const supabase = getSupabaseClient();
        const { data: sessionData } = await supabase.auth.getSession();
        if (!sessionData.session) {
          router.replace("/signin");
          return;
        }
        const fullName =
          (sessionData.session.user.user_metadata?.full_name as string | undefined) ??
          (sessionData.session.user.user_metadata?.name as string | undefined) ??
          null;
        setAccountLabel(getAccountLabel(fullName, sessionData.session.user.email ?? null));

        const api = createApiClient(sessionData.session.access_token);
        const [{ data: historyData, error: historyError }, { data: usageData, error: usageError }] =
          await Promise.all([api.GET("/billing/history"), api.GET("/billing/usage")]);

        if (historyError) {
          setError(getApiErrorMessage(historyError, "Unable to load history."));
          return;
        }

        if (usageError) {
          setError(getApiErrorMessage(usageError, "Unable to load usage."));
          return;
        }

        setHistory(historyData ?? []);
        setUsageRemaining(usageData?.total_remaining_seconds ?? null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      } finally {
        setLoading(false);
      }
    };

    void loadHistory();
  }, [router]);

  const handleSignOut = async () => {
    const supabase = getSupabaseClient();
    await supabase.auth.signOut();
    router.replace("/signin");
  };

  if (loading) {
    return (
      <div className={styles.page}>
        <AppShellHeader active="history" remainingSeconds={usageRemaining} accountLabel={accountLabel} onSignOut={handleSignOut} />
        <main className={styles.main}>
          <div className={styles.card}>
            <h1 className={styles.cardTitle}>Loading history…</h1>
            <p className={styles.cardText}>Pulling your recent usage.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <AppShellHeader active="history" remainingSeconds={usageRemaining} accountLabel={accountLabel} onSignOut={handleSignOut} />

      <main className={styles.main}>
        <section className={styles.card}>
          <div className={styles.sectionHeader}>
            <div>
              <h1 className={styles.cardTitle}>Usage history</h1>
              <p className={styles.cardText}>A quick log of your recent summaries.</p>
            </div>
          </div>

          {history.length === 0 ? (
            <p className={styles.cardText}>No usage yet. Run your first summary to populate this list.</p>
          ) : (
            <div className={styles.historyList}>
              {history.map((entry, index) => (
                <div className={styles.historyRow} key={`${entry.job_id ?? "job"}-${index}`}>
                  <div>
                    <p className={styles.historyTitle}>
                      {entry.source === "subscription" ? "Subscription usage" : "Pack usage"}
                    </p>
                    <p className={styles.cardText}>Job: {entry.job_id ?? "—"}</p>
                  </div>
                  <div className={styles.historyMeta}>
                    <span>{formatDuration(entry.seconds_used)}</span>
                    <span>{formatDate(entry.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {error ? <p className={styles.status}>{error}</p> : null}
        </section>
      </main>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { UsageHistoryEntry } from "@fathom/api-client";
import { createApiClient } from "@fathom/api-client";

import styles from "../app.module.css";
import { formatDate, formatDuration } from "../../lib/format";
import { getSupabaseClient } from "../../lib/supabaseClient";
import { getApiErrorMessage } from "../../lib/apiErrors";

export default function HistoryPage() {
  const router = useRouter();
  const [history, setHistory] = useState<UsageHistoryEntry[]>([]);
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

        const api = createApiClient(sessionData.session.access_token);
        const { data, error: apiError } = await api.GET("/billing/history");
        if (apiError) {
          setError(getApiErrorMessage(apiError, "Unable to load history."));
          return;
        }

        setHistory(data ?? []);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      } finally {
        setLoading(false);
      }
    };

    void loadHistory();
  }, [router]);

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
            <h1 className={styles.cardTitle}>Loading history…</h1>
            <p className={styles.cardText}>Pulling your recent usage.</p>
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
          <Link className={styles.button} href="/app">
            Back to app
          </Link>
        </div>
      </header>

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

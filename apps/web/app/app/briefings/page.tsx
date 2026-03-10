"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { UsageHistoryEntry } from "@fathom/api-client";
import type { User } from "@supabase/supabase-js";
import { createApiClient } from "@fathom/api-client";

import { AppShellHeader } from "../../components/AppShellHeader";
import chrome from "../../components/app-chrome.module.css";
import styles from "../app.module.css";
import { formatDate, formatDuration } from "../../lib/format";
import { getSupabaseClient } from "../../lib/supabaseClient";
import { getApiErrorMessage } from "../../lib/apiErrors";
import { getAccountLabel } from "../../lib/accountLabel";

function formatBriefingCount(count: number): string {
  return `${count} ${count === 1 ? "briefing" : "briefings"}`;
}

export default function BriefingsPage() {
  const router = useRouter();
  const [briefings, setBriefings] = useState<UsageHistoryEntry[]>([]);
  const [usageRemaining, setUsageRemaining] = useState<number | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadBriefings = async () => {
      try {
        const supabase = getSupabaseClient();
        const { data: sessionData } = await supabase.auth.getSession();
        if (!sessionData.session) {
          router.replace("/signin");
          return;
        }

        setUser(sessionData.session.user);

        const api = createApiClient(sessionData.session.access_token);
        const [{ data: historyData, error: historyError }, { data: usageData, error: usageError }] = await Promise.all([
          api.GET("/billing/history"),
          api.GET("/billing/usage")
        ]);

        if (historyError) {
          setError(getApiErrorMessage(historyError, "Unable to load your briefings."));
          return;
        }

        if (usageError) {
          setError(getApiErrorMessage(usageError, "Unable to load usage."));
          return;
        }

        setBriefings(historyData ?? []);
        setUsageRemaining(usageData?.total_remaining_seconds ?? null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      } finally {
        setLoading(false);
      }
    };

    void loadBriefings();
  }, [router]);

  const handleSignOut = async () => {
    const supabase = getSupabaseClient();
    await supabase.auth.signOut();
    router.replace("/signin");
  };

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader
        active="briefings"
        remainingSeconds={usageRemaining}
        accountLabel={getAccountLabel(user)}
        onSignOut={handleSignOut}
      />

      <main className={chrome.mainFrame}>
        <section className={chrome.heroBlock}>
          <div>
            <p className={chrome.heroEyebrow}>Briefings</p>
            <h1 className={chrome.heroTitle}>Your briefings</h1>
            <p className={chrome.heroText}>A clear record of the podcasts you&apos;ve turned into briefings.</p>
          </div>
          <div className={chrome.heroMeta}>
            <span className={chrome.statusPillMuted}>Available {formatDuration(usageRemaining ?? 0)}</span>
            <span className={chrome.statusPillMuted}>{loading ? "Syncing" : formatBriefingCount(briefings.length)}</span>
          </div>
        </section>

        <section className={chrome.surface}>
          <div className={chrome.surfaceHeader}>
            <div>
              <h2 className={chrome.surfaceTitle}>Recent</h2>
            </div>
          </div>

          {loading ? (
            <p className={chrome.emptyState}>Loading your briefings…</p>
          ) : briefings.length === 0 ? (
            <p className={chrome.emptyState}>No briefings yet. Start your first one from the workspace.</p>
          ) : (
            <div className={`${chrome.list} ${styles.briefingsList}`}>
              {briefings.map((entry, index) => (
                <article className={chrome.listRow} key={`${entry.job_id ?? "job"}-${index}`}>
                  <div className={chrome.listPrimary}>
                    <p className={chrome.listTitle}>{entry.title ?? "Untitled podcast briefing"}</p>
                    <p className={chrome.listMeta}>{formatDate(entry.created_at)}</p>
                  </div>
                  <div className={chrome.listAside}>
                    <span>{formatDuration(entry.seconds_used)} used</span>
                  </div>
                </article>
              ))}
            </div>
          )}

          {error ? <p className={`${chrome.inlineStatus} ${chrome.inlineStatusError}`}>{error}</p> : null}
        </section>
      </main>
    </div>
  );
}

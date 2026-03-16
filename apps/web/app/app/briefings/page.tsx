"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { UsageHistoryEntry } from "@fathom/api-client";

import { AppShellHeader } from "../../components/AppShellHeader";
import { useAppShell } from "../../components/AppShellProvider";
import chrome from "../../components/app-chrome.module.css";
import styles from "../app.module.css";
import { formatDateTime, formatDuration } from "../../lib/format";
import { getApiErrorMessage } from "../../lib/apiErrors";
import { getAccountLabel } from "../../lib/accountLabel";
import {
  getCachedBriefings,
  hasFreshBriefingsCache,
  loadBriefings,
  prefetchSessionSnapshot
} from "../../lib/appDataCache";

function formatBriefingCount(count: number): string {
  return `${count} ${count === 1 ? "briefing" : "briefings"}`;
}

function getSessionIdFromPath(path: string | null | undefined): string | null {
  if (!path) {
    return null;
  }

  const match = path.match(/\/app\/briefings\/sessions\/([^/?#]+)/);
  return match?.[1] ?? null;
}

export default function BriefingsPage() {
  const { accessToken, loading: shellLoading, remainingSeconds, signOut, user } = useAppShell();
  const [briefings, setBriefings] = useState<UsageHistoryEntry[]>(getCachedBriefings() ?? []);
  const [loading, setLoading] = useState(() => getCachedBriefings() === null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) {
      return;
    }

    let active = true;
    const cacheIsFresh = hasFreshBriefingsCache();

    if (cacheIsFresh) {
      setBriefings(getCachedBriefings() ?? []);
      setLoading(false);
      setError(null);
      return;
    }

    const syncBriefings = async () => {
      try {
        const normalizedBriefings = await loadBriefings(accessToken);

        if (active) {
          setBriefings(normalizedBriefings);
          setError(null);
        }
      } catch (err) {
        if (active) {
          setError(getApiErrorMessage(err, "Unable to load your briefings."));
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void syncBriefings();

    return () => {
      active = false;
    };
  }, [accessToken]);

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader
        active="briefings"
        remainingSeconds={remainingSeconds}
        accountLabel={getAccountLabel(user)}
        onSignOut={signOut}
      />

      <main className={chrome.mainFrame}>
        <section className={`${chrome.heroBlock} ${styles.pageColumn}`}>
          <div>
            <p className={chrome.heroEyebrow}>Briefings</p>
            <h1 className={chrome.heroTitle}>Your briefings</h1>
            <p className={chrome.heroText}>A clear record of the podcasts you&apos;ve turned into briefings.</p>
          </div>
          <div className={chrome.heroMeta}>
            <span className={chrome.statusPillMuted}>Available {formatDuration(remainingSeconds ?? 0)}</span>
            <span className={chrome.statusPillMuted}>{loading || shellLoading ? "Syncing" : formatBriefingCount(briefings.length)}</span>
          </div>
        </section>

        <section className={`${chrome.surface} ${styles.pageColumn} ${styles.briefingsSurface}`}>
          <div className={chrome.surfaceHeader}>
            <div>
              <h2 className={chrome.surfaceTitle}>Recent</h2>
            </div>
          </div>

          {loading && briefings.length === 0 ? (
            <p className={chrome.emptyState}>Loading your briefings…</p>
          ) : briefings.length === 0 ? (
            <p className={chrome.emptyState}>No briefings yet. Start your first one from the workspace.</p>
          ) : (
            <div className={`${chrome.list} ${styles.briefingsList}`}>
              {briefings.map((entry, index) => (
                <Link
                  className={chrome.listRow}
                  href={entry.session_path ?? "/app"}
                  key={`${entry.job_id ?? "job"}-${index}`}
                  onMouseEnter={() => {
                    const sessionId = getSessionIdFromPath(entry.session_path);
                    if (!accessToken || !sessionId) {
                      return;
                    }
                    void prefetchSessionSnapshot(accessToken, sessionId);
                  }}
                  onFocus={() => {
                    const sessionId = getSessionIdFromPath(entry.session_path);
                    if (!accessToken || !sessionId) {
                      return;
                    }
                    void prefetchSessionSnapshot(accessToken, sessionId);
                  }}
                >
                  <div className={chrome.listPrimary}>
                    <p className={chrome.listTitle}>{entry.title ?? "Untitled podcast briefing"}</p>
                    <p className={chrome.listMeta}>{formatDateTime(entry.created_at)}</p>
                  </div>
                  <div className={chrome.listAside}>
                    <span>{formatDuration(entry.seconds_used)} used</span>
                  </div>
                </Link>
              ))}
            </div>
          )}

          {error ? <p className={`${chrome.inlineStatus} ${chrome.inlineStatusError}`}>{error}</p> : null}
        </section>
      </main>
    </div>
  );
}

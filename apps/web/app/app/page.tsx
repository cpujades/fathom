"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { User } from "@supabase/supabase-js";

import { AppShellHeader } from "../components/AppShellHeader";
import { useAppShell } from "../components/AppShellProvider";
import chrome from "../components/app-chrome.module.css";
import { getAccountLabel } from "../lib/accountLabel";
import { formatDuration } from "../lib/format";
import styles from "./home.module.css";

const DEFAULT_QUOTA_SECONDS = 8 * 60 * 60;

function getFirstName(user: Pick<User, "user_metadata"> | null): string | null {
  const fullName =
    (user?.user_metadata?.full_name as string | undefined) ?? (user?.user_metadata?.name as string | undefined);

  if (!fullName) {
    return null;
  }

  const firstName = fullName
    .trim()
    .split(/\s+/)
    .find(Boolean);

  return firstName && firstName.length > 0 ? firstName : null;
}

export default function AppHome() {
  const router = useRouter();
  const { loading, remainingSeconds, signOut, user } = useAppShell();
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    router.prefetch("/app/briefings/new");
    router.prefetch("/app/briefings");
  }, [router]);

  const handleSubmit = () => {
    if (submitting) {
      return;
    }

    if (!url.trim()) {
      setError("Paste a valid podcast or YouTube URL to start a briefing.");
      return;
    }

    setError(null);
    setSubmitting(true);
    router.push(`/app/briefings/new?url=${encodeURIComponent(url.trim())}`);
  };

  const handleFormSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    handleSubmit();
  };

  const firstName = getFirstName(user);
  const workspaceTitle = loading
    ? "Loading your desk..."
    : firstName
      ? `What podcast is worth exploring, ${firstName}?`
      : "What podcast is worth exploring?";
  const quotaLabel = useMemo(() => {
    if (remainingSeconds === null) {
      return "Checking";
    }
    if (remainingSeconds <= 0) {
      return "0m";
    }
    return formatDuration(remainingSeconds);
  }, [remainingSeconds]);
  const quotaPercentLabel = useMemo(() => {
    if (remainingSeconds === null) {
      return "—";
    }
    return `${Math.max(0, Math.min(100, Math.round((remainingSeconds / DEFAULT_QUOTA_SECONDS) * 100)))}%`;
  }, [remainingSeconds]);
  const quotaPercent = useMemo(() => {
    if (remainingSeconds === null) {
      return 0;
    }
    return Math.max(0, Math.min(100, Math.round((remainingSeconds / DEFAULT_QUOTA_SECONDS) * 100)));
  }, [remainingSeconds]);
  const canSubmit = !loading && !submitting && (remainingSeconds === null || remainingSeconds > 0);

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader
        active="home"
        remainingSeconds={remainingSeconds}
        accountLabel={getAccountLabel(user)}
        onSignOut={signOut}
      />

      <main id="main-content" className={chrome.mainFrame}>
        <section className={styles.workspaceShell}>
          <article className={`${chrome.surfaceStrong} ${styles.workspacePanel}`}>
            <h1 className={styles.workspaceTitle}>{workspaceTitle}</h1>

            <form className={styles.commandBlock} onSubmit={handleFormSubmit}>
              <div className={styles.commandRow}>
                <div className={styles.commandField}>
                  <input
                    className={`${chrome.input} ${styles.commandInput}`}
                    type="url"
                    placeholder="Paste a YouTube or podcast URL"
                    aria-label="Podcast or YouTube URL"
                    value={url}
                    onChange={(event) => setUrl(event.target.value)}
                    disabled={loading}
                  />
                </div>
                <div className={styles.commandActions}>
                  <button
                    className={`${chrome.primaryButton} ${styles.commandButton}`}
                    type="submit"
                    disabled={!canSubmit}
                  >
                    {submitting ? "Starting..." : "Start briefing"}
                  </button>
                  <div className={styles.quotaBadge} aria-label={`${quotaLabel} listening time available`}>
                    <span
                      className={styles.quotaRing}
                      style={{ "--quota-percent": `${quotaPercent}%` } as React.CSSProperties}
                      aria-hidden="true"
                    />
                    <span className={styles.quotaValue}>{quotaPercentLabel}</span>
                  </div>
                </div>
              </div>
              <div className={styles.commandMetaRow}>
                {remainingSeconds !== null && remainingSeconds <= 0 ? (
                  <Link href="/app/billing#billing-offers">Add time</Link>
                ) : null}
              </div>
              {error ? <p className={`${chrome.inlineStatus} ${chrome.inlineStatusError}`}>{error}</p> : null}
            </form>
          </article>
        </section>
      </main>
    </div>
  );
}

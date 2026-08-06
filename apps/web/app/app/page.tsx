"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { User } from "@supabase/supabase-js";

import { AppShellHeader } from "../components/AppShellHeader";
import { useAppShell } from "../components/AppShellProvider";
import chrome from "../components/app-chrome";
import { getAccountLabel } from "../lib/accountLabel";
import { formatDuration, formatExactDuration } from "../lib/format";
import {
  getBillingOffersAction,
  getLowBalanceSeconds,
  resolveCurrentUsageBalance
} from "../lib/usage";
import { getCreationAccessState } from "./usagePresentation";
import styles from "./home.module.css";

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
  const {
    debtSeconds,
    hasActivePaidSubscription,
    isBlocked,
    loading,
    remainingSeconds,
    signOut,
    usageRefreshFailed,
    user
  } = useAppShell();
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
      setError("Paste a valid public YouTube URL to start a briefing.");
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
      ? `What is worth understanding, ${firstName}?`
      : "What is worth understanding?";
  const refreshedUsage = resolveCurrentUsageBalance(null, {
    debtSeconds,
    isBlocked,
    remainingSeconds
  });
  const availableSeconds = refreshedUsage?.total_remaining_seconds ?? remainingSeconds;
  const quotaLabel = useMemo(() => {
    if (availableSeconds === null) {
      return "Checking";
    }
    if (availableSeconds <= 0) {
      return "0m";
    }
    return formatDuration(availableSeconds);
  }, [availableSeconds]);
  const creationAccess = getCreationAccessState(refreshedUsage);
  const lowBalanceSeconds = getLowBalanceSeconds(refreshedUsage);
  const billingAction = getBillingOffersAction(
    hasActivePaidSubscription
  );
  const usageNotice = refreshedUsage?.is_blocked
    ? `Briefing creation is paused because the debt limit has been reached. Add video time to repay ${formatDuration(creationAccess.debtSeconds)} and continue.`
    : creationAccess.debtSeconds > 0
      ? `Outstanding video time: ${formatDuration(creationAccess.debtSeconds)}. New credits repay this first, and Talven checks each source length before starting.`
      : creationAccess.hasNoCredits
        ? "No video time remains. Add time to start another briefing."
        : lowBalanceSeconds !== null
          ? `Only ${formatExactDuration(lowBalanceSeconds)} of video time remain. Add time now so your next briefing is not interrupted.`
          : null;
  const canSubmit = !loading && !submitting && creationAccess.canCreate;
  const inputDescriptionIds = [error ? "briefing-source-error" : null, usageNotice ? "briefing-usage-notice" : null]
    .filter(Boolean)
    .join(" ") || undefined;

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
                  <label className={styles.commandLabel} htmlFor="briefing-source-url">
                    Public YouTube URL
                  </label>
                  <input
                    className={`${chrome.input} ${styles.commandInput}`}
                    id="briefing-source-url"
                    type="url"
                    placeholder="Paste a public YouTube URL"
                    aria-describedby={inputDescriptionIds}
                    aria-invalid={error ? true : undefined}
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
                  <div className={styles.quotaBadge} aria-label={`${quotaLabel} video time available`}>
                    <span className={styles.quotaValue}>{quotaLabel}</span>
                  </div>
                </div>
              </div>
              <div
                className={`${styles.commandMetaRow} ${lowBalanceSeconds !== null ? styles.lowBalanceNotice : ""}`}
              >
                {usageNotice ? (
                  <p id="briefing-usage-notice" role={refreshedUsage?.is_blocked ? "alert" : "status"}>
                    {usageNotice}
                  </p>
                ) : (
                  <span>Video time is charged only after a briefing is completed successfully.</span>
                )}
                {refreshedUsage?.is_blocked || creationAccess.hasNoCredits || lowBalanceSeconds !== null ? (
                  <Link href={billingAction.href}>{billingAction.label}</Link>
                ) : null}
              </div>
              {usageRefreshFailed ? (
                <p className={styles.usageRefreshNote} role="status">
                  Live debt details could not be refreshed. Talven will still verify access before starting.
                </p>
              ) : null}
              {error ? (
                <p
                  className={`${chrome.inlineStatus} ${chrome.inlineStatusError}`}
                  id="briefing-source-error"
                  role="alert"
                >
                  {error}
                </p>
              ) : null}
            </form>
          </article>
        </section>
      </main>
    </div>
  );
}

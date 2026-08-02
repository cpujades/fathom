"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { User } from "@supabase/supabase-js";
import { createApiClient, type UsageOverviewResponse } from "@fathom/api-client";

import { AppShellHeader } from "../components/AppShellHeader";
import { useAppShell } from "../components/AppShellProvider";
import chrome from "../components/app-chrome";
import { getAccountLabel } from "../lib/accountLabel";
import {
  assertAuthenticatedRequestScopeCurrent,
  captureAuthenticatedRequestScope,
  isAuthenticatedDataScopeChangedError
} from "../lib/appDataCache";
import { formatDuration } from "../lib/format";
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
  const { accessToken, loading, remainingSeconds, signOut, user } = useAppShell();
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [usageResult, setUsageResult] = useState<{
    data: UsageOverviewResponse | null;
    failed: boolean;
    userId: string;
  } | null>(null);
  const userId = user?.id ?? null;

  useEffect(() => {
    router.prefetch("/app/briefings/new");
    router.prefetch("/app/briefings");
  }, [router]);

  useEffect(() => {
    if (!accessToken || !userId) {
      return;
    }

    let active = true;
    const requestScope = captureAuthenticatedRequestScope(userId);

    const loadUsage = async () => {
      try {
        const api = createApiClient(accessToken);
        const { data, error: apiError } = await api.GET("/billing/usage");
        assertAuthenticatedRequestScopeCurrent(requestScope);
        if (!active) {
          return;
        }
        if (apiError || !data) {
          setUsageResult({ userId, data: null, failed: true });
          return;
        }
        setUsageResult({ userId, data, failed: false });
      } catch (caught) {
        if (active && !isAuthenticatedDataScopeChangedError(caught)) {
          setUsageResult({ userId, data: null, failed: true });
        }
      }
    };

    void loadUsage();
    return () => {
      active = false;
    };
  }, [accessToken, userId]);

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
  const usage = usageResult?.userId === userId ? usageResult.data : null;
  const usageRefreshFailed = usageResult?.userId === userId && usageResult.failed;
  const availableSeconds = usage?.total_remaining_seconds ?? remainingSeconds;
  const quotaLabel = useMemo(() => {
    if (availableSeconds === null) {
      return "Checking";
    }
    if (availableSeconds <= 0) {
      return "0m";
    }
    return formatDuration(availableSeconds);
  }, [availableSeconds]);
  const creationAccess = getCreationAccessState(usage);
  const usageNotice = usage?.is_blocked
    ? `Briefing creation is paused because the debt limit has been reached. Add video time to repay ${formatDuration(creationAccess.debtSeconds)} and continue.`
    : creationAccess.debtSeconds > 0
      ? `Outstanding video time: ${formatDuration(creationAccess.debtSeconds)}. New credits repay this first, and Talven checks each source length before starting.`
      : creationAccess.hasNoCredits
        ? "No video time remains. Add time to start another briefing."
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
              <div className={styles.commandMetaRow}>
                {usageNotice ? (
                  <p id="briefing-usage-notice" role={usage?.is_blocked ? "alert" : "status"}>
                    {usageNotice}
                  </p>
                ) : (
                  <span>Video time is charged only after a briefing is completed successfully.</span>
                )}
                {usage?.is_blocked || creationAccess.hasNoCredits ? (
                  <Link href="/app/billing#billing-offers">Add time</Link>
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

"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { createApiClient } from "@fathom/api-client";

import { AppShellHeader } from "../../../components/AppShellHeader";
import { useAppShell } from "../../../components/AppShellProvider";
import chrome from "../../../components/app-chrome.module.css";
import { getApiErrorMessage } from "../../../lib/apiErrors";
import { getAccountLabel } from "../../../lib/accountLabel";
import { cacheSessionSnapshot, invalidateBriefingsCache } from "../../../lib/appDataCache";
import { buildSignInPath } from "../../../lib/url";
import styles from "../session.module.css";

function BriefingCreatePageContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { accessToken, loading, remainingSeconds, signOut, user } = useAppShell();
  const initialUrl = useMemo(() => searchParams.get("url")?.trim() ?? "", [searchParams]);
  const [draftUrl, setDraftUrl] = useState(initialUrl);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const startedRef = useRef(false);
  const signInPath = buildSignInPath(
    `${pathname}${searchParams.toString() ? `?${searchParams.toString()}` : ""}`
  );

  useEffect(() => {
    setDraftUrl(initialUrl);
  }, [initialUrl]);

  const startSession = useCallback(
    async (rawUrl: string) => {
      if (!accessToken || submitting) {
        return;
      }

      setSubmitting(true);
      setError(null);

      try {
        const api = createApiClient(accessToken);
        const { data, error: apiError } = await api.POST("/briefing-sessions", {
          body: {
            url: rawUrl
          }
        });

        if (apiError) {
          setError(getApiErrorMessage(apiError, "Unable to start the briefing."));
          return;
        }

        if (data?.session_id) {
          cacheSessionSnapshot(data);
          if (data.resolution_type === "reused_ready") {
            invalidateBriefingsCache();
          }
          router.replace(`/app/briefings/sessions/${data.session_id}`);
          return;
        }

        setError("Unexpected response from the server.");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      } finally {
        setSubmitting(false);
      }
    },
    [accessToken, router, submitting]
  );

  useEffect(() => {
    if (loading || startedRef.current) {
      return;
    }
    if (!accessToken) {
      router.replace(signInPath);
      return;
    }

    startedRef.current = true;

    if (!initialUrl) {
      setError("No source link reached this step. Paste one below to continue.");
      return;
    }

    void startSession(initialUrl);
  }, [accessToken, initialUrl, loading, router, signInPath, startSession]);

  const handleRetry = async () => {
    const nextUrl = draftUrl.trim();
    if (!nextUrl) {
      setError("Paste a valid podcast or YouTube URL to start a briefing.");
      return;
    }

    await startSession(nextUrl);
  };

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader
        active={null}
        remainingSeconds={remainingSeconds}
        accountLabel={getAccountLabel(user)}
        onSignOut={signOut}
      />

      <main className={chrome.mainFrame}>
        <section className={chrome.heroBlock}>
          <div>
            <p className={chrome.heroEyebrow}>Briefing</p>
            <h1 className={chrome.heroTitle}>Starting your briefing</h1>
            <p className={chrome.heroText}>Talven is opening a live session and checking for reusable work first.</p>
          </div>
          <div className={chrome.heroActions}>
            <Link className={chrome.ghostButton} href="/app">
              Back to workspace
            </Link>
          </div>
        </section>

        <section className={`${chrome.surfaceStrong} ${styles.loadingCard}`}>
          <div className={styles.loadingTop}>
            <div>
              <h2 className={chrome.surfaceTitle}>Creating your session</h2>
              <p className={chrome.surfaceText}>This should take just a moment.</p>
            </div>
            <span className={chrome.statusPillMuted}>Starting</span>
          </div>

          <div className={chrome.progressTrack}>
            <div className={chrome.progressFill} style={{ width: "12%" }} />
          </div>

          <div className={chrome.stepList}>
            <div className={chrome.stepRow}>
              <span className={chrome.stepDotActive} />
              <div>
                <p className={chrome.stepLabel}>{initialUrl ? "Opening a session" : "Waiting for a source"}</p>
                <p className={chrome.stepHint}>
                  {initialUrl
                    ? "Talven is validating the source and connecting you to live updates."
                    : "Paste a source link to continue directly from here."}
                </p>
              </div>
            </div>
          </div>

          {error ? (
            <div className={styles.errorCard}>
              <p>{error}</p>
              <label className={chrome.fieldStack}>
                <span className={chrome.fieldLabel}>Podcast or YouTube URL</span>
                <input
                  className={chrome.input}
                  type="url"
                  value={draftUrl}
                  onChange={(event) => setDraftUrl(event.target.value)}
                  placeholder="https://www.youtube.com/watch?v=..."
                  disabled={submitting}
                />
              </label>
              <div className={chrome.actionRow}>
                <button className={chrome.primaryButton} type="button" onClick={() => void handleRetry()} disabled={submitting}>
                  {submitting ? "Starting briefing..." : "Start briefing"}
                </button>
                <Link className={chrome.secondaryButton} href="/app">
                  Back to workspace
                </Link>
              </div>
              {isCreditError(error) ? (
                <div className={chrome.actionRow}>
                  <Link className={chrome.primaryButton} href="/app/billing#billing-offers">
                    Get more listening time
                  </Link>
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
      </main>
    </div>
  );
}

export default function BriefingCreatePage() {
  return (
    <Suspense
      fallback={
        <div className={chrome.pageFrame}>
          <main className={chrome.mainFrame}>
            <section className={`${chrome.surfaceStrong} ${styles.loadingCard}`}>
              <div className={styles.loadingTop}>
                <div>
                  <h2 className={chrome.surfaceTitle}>Starting your briefing</h2>
                  <p className={chrome.surfaceText}>Preparing the request details.</p>
                </div>
              </div>
            </section>
          </main>
        </div>
      }
    >
      <BriefingCreatePageContent />
    </Suspense>
  );
}

function isCreditError(message: string): boolean {
  const normalized = message.toLowerCase();
  return normalized.includes("insufficient credits") || normalized.includes("no remaining credits");
}

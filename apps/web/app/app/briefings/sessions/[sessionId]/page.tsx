"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { createApiClient, getApiBaseUrl, type BriefingSessionResponse } from "@fathom/api-client";

import { AppShellHeader } from "../../../../components/AppShellHeader";
import { StreamingMarkdown } from "../../../../components/StreamingMarkdown";
import { useAppShell } from "../../../../components/AppShellProvider";
import chrome from "../../../../components/app-chrome.module.css";
import { getApiErrorMessage } from "../../../../lib/apiErrors";
import { getAccountLabel } from "../../../../lib/accountLabel";
import { cacheSessionSnapshot, getCachedSessionSnapshot } from "../../../../lib/appDataCache";
import { readSessionStream, type SessionStreamEvent } from "../../sessionStream";
import styles from "../../session.module.css";

const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 5000;
const RECONCILE_INTERVAL_MS = 4000;

const STATE_LABELS: Record<BriefingSessionResponse["state"], string> = {
  accepted: "Briefing accepted",
  resolving_source: "Resolving the source",
  reusing_existing: "Checking reusable work",
  transcribing: "Listening carefully",
  drafting_briefing: "Drafting the briefing",
  finalizing_briefing: "Finalizing the briefing",
  ready: "Briefing ready",
  failed: "Needs attention"
};

export default function BriefingSessionPage() {
  const router = useRouter();
  const params = useParams();
  const sessionId = useMemo(() => params?.sessionId?.toString() ?? "", [params]);
  const cachedSnapshot = useMemo(
    () => (sessionId ? getCachedSessionSnapshot(sessionId) : null),
    [sessionId]
  );
  const { accessToken, loading, remainingSeconds, signOut, user } = useAppShell();
  const [session, setSession] = useState<BriefingSessionResponse | null>(cachedSnapshot);
  const [initialSnapshotLoaded, setInitialSnapshotLoaded] = useState(Boolean(cachedSnapshot));
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(cachedSnapshot?.progress ?? 5);
  const lastEventIdRef = useRef<string | null>(null);
  const terminalStateRef = useRef(false);
  const lastStreamActivityRef = useRef<number>(Date.now());

  useEffect(() => {
    if (loading || !sessionId) {
      return;
    }
    if (!accessToken) {
      router.replace("/signin");
      return;
    }

    lastEventIdRef.current = null;
    lastStreamActivityRef.current = Date.now();
    setPdfUrl(null);
    setPdfError(null);
    setError(null);

    const prefetchedSnapshot = getCachedSessionSnapshot(sessionId);
    if (prefetchedSnapshot) {
      setSession(prefetchedSnapshot);
      setInitialSnapshotLoaded(true);
      setProgress(prefetchedSnapshot.progress);
      terminalStateRef.current = prefetchedSnapshot.state === "ready" || prefetchedSnapshot.state === "failed";
    } else {
      terminalStateRef.current = false;
      setInitialSnapshotLoaded(false);
      setSession(null);
      setProgress(5);
    }

    const abortController = new AbortController();
    const api = createApiClient(accessToken);

    const handleSessionSnapshot = (snapshot: BriefingSessionResponse) => {
      cacheSessionSnapshot(snapshot);
      setSession(snapshot);
      setProgress(snapshot.progress);
      setInitialSnapshotLoaded(true);
      terminalStateRef.current = snapshot.state === "ready" || snapshot.state === "failed";
      lastStreamActivityRef.current = Date.now();
    };

    const handleStreamEvent = async (
      event: SessionStreamEvent<BriefingSessionResponse>
    ) => {
      if (!event.data) {
        return;
      }

      lastEventIdRef.current = event.id;
      lastStreamActivityRef.current = Date.now();
      handleSessionSnapshot(event.data);
      setError(null);
    };

    const refreshSessionSnapshot = async (currentSessionId: string) => {
      const { data, error: apiError } = await api.GET("/briefing-sessions/{session_id}", {
        params: {
          path: {
            session_id: currentSessionId
          }
        }
      });

      if (apiError) {
        setInitialSnapshotLoaded(true);
        setError(getApiErrorMessage(apiError, "Unable to fetch briefing session."));
        return null;
      }

      if (data) {
        handleSessionSnapshot(data);
        setError(null);
      }

      return data ?? null;
    };

    const streamSession = async () => {
      let data = prefetchedSnapshot;
      if (!data) {
        data = await refreshSessionSnapshot(sessionId);
      } else if (data.state !== "ready" && data.state !== "failed") {
        void refreshSessionSnapshot(sessionId);
      }

      if (!data) {
        setInitialSnapshotLoaded(true);
        setError("Unable to load the briefing session.");
        return;
      }

      if (data.state === "ready" || data.state === "failed") {
        return;
      }

      let reconnectDelay = RECONNECT_BASE_DELAY_MS;
      let reconcileTimer: number | null = null;

      try {
        reconcileTimer = window.setInterval(() => {
          if (terminalStateRef.current || abortController.signal.aborted) {
            return;
          }

          if (Date.now() - lastStreamActivityRef.current < RECONCILE_INTERVAL_MS) {
            return;
          }

          void refreshSessionSnapshot(sessionId);
        }, RECONCILE_INTERVAL_MS);

        while (!abortController.signal.aborted) {
          try {
            const headers = new Headers({
              Accept: "text/event-stream",
              Authorization: `Bearer ${accessToken}`
            });
            if (lastEventIdRef.current) {
              headers.set("Last-Event-ID", lastEventIdRef.current);
            }

            const response = await fetch(new URL(data.events_url, getApiBaseUrl()).toString(), {
              headers,
              cache: "no-store",
              signal: abortController.signal
            });

            if (!response.ok || !response.body) {
              throw new Error(`Unable to open the live session stream (${response.status}).`);
            }

            reconnectDelay = RECONNECT_BASE_DELAY_MS;
            await readSessionStream<BriefingSessionResponse>(response.body, async (event) => {
              await handleStreamEvent(event);
            });

            if (terminalStateRef.current || abortController.signal.aborted) {
              return;
            }
          } catch (streamError) {
            if (abortController.signal.aborted) {
              return;
            }
            setError(streamError instanceof Error ? streamError.message : "The live stream disconnected.");
          }

          if (terminalStateRef.current || abortController.signal.aborted) {
            return;
          }

          await sleep(reconnectDelay, abortController.signal);
          reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_DELAY_MS);
        }
      } finally {
        if (reconcileTimer !== null) {
          window.clearInterval(reconcileTimer);
        }
      }
    };

    void streamSession();

    return () => {
      abortController.abort();
    };
  }, [accessToken, loading, router, sessionId]);

  const handlePdfAction = async () => {
    if (!session?.briefing_id || !accessToken) {
      return;
    }

    setPdfError(null);
    setPdfLoading(true);

    try {
      const api = createApiClient(accessToken);
      const briefingId = String(session.briefing_id);
      const response = session.briefing_has_pdf
        ? await api.GET("/briefings/{briefing_id}", {
            params: {
              path: {
                briefing_id: briefingId
              }
            }
          })
        : await api.POST("/briefings/{briefing_id}/pdf", {
            params: {
              path: {
                briefing_id: briefingId
              }
            }
          });

      const data = response.data;
      const apiError = response.error;

      if (apiError) {
        setPdfError(
          getApiErrorMessage(apiError, session.briefing_has_pdf ? "Unable to load the PDF." : "Unable to generate the PDF.")
        );
        return;
      }

      const nextPdfUrl = data?.pdf_url ?? null;
      setPdfUrl(nextPdfUrl);
      if (nextPdfUrl) {
        window.open(nextPdfUrl, "_blank", "noopener,noreferrer");
      }
    } catch (err) {
      setPdfError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setPdfLoading(false);
    }
  };

  const isReady = session?.state === "ready";
  const isFailed = session?.state === "failed";
  const isFinalizing = session?.state === "finalizing_briefing";
  const markdownToRender = session?.briefing_markdown ?? "";
  const hasMarkdown = Boolean(markdownToRender);
  const clampedProgress = Math.max(0, Math.min(progress, 100));
  const stageLabel = session ? STATE_LABELS[session.state] : "Preparing your briefing";
  const headline = isReady
    ? "Briefing ready"
    : isFailed
      ? "Briefing failed"
      : hasMarkdown
        ? "Briefing in progress"
        : "Preparing your briefing";
  const subhead = isReady
    ? "Your briefing is ready to read, export, and move into the rest of your work."
    : isFailed
      ? "We ran into an issue. You can start again or return to the workspace."
      : "Talven is turning the source into a clean, readable briefing.";
  const showProgressPanel = initialSnapshotLoaded && !hasMarkdown && !isReady && !isFailed;
  const showCreditCta = Boolean(error && isCreditError(error));
  const activeStepIndex = isReady || isFinalizing ? 2 : clampedProgress >= 60 ? 1 : 0;
  const canShowReader = initialSnapshotLoaded && (hasMarkdown || isReady || isFailed);
  const primaryPdfActionLabel = pdfLoading
    ? session?.briefing_has_pdf
      ? "Opening PDF..."
      : "Preparing PDF..."
    : session?.briefing_has_pdf || pdfUrl
      ? "Download PDF"
      : "Generate PDF";

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
            <h1 className={chrome.heroTitle}>{headline}</h1>
            <p className={chrome.heroText}>{subhead}</p>
          </div>
          <div className={chrome.heroMeta}>
            <span className={chrome.statusPill}>{stageLabel}</span>
            <span
              className={
                isReady
                  ? chrome.statusPillSuccess
                  : isFailed
                    ? chrome.statusPillDanger
                    : `${chrome.statusPillMuted} ${styles.liveStatus}`
              }
            >
              {isReady ? "Final" : isFailed ? "Failed" : "Live"}
            </span>
          </div>
        </section>

        {!initialSnapshotLoaded ? (
          <section className={`${chrome.surfaceStrong} ${styles.loadingCard}`}>
            <div className={styles.loadingTop}>
              <div>
                <h2 className={chrome.surfaceTitle}>Opening your briefing</h2>
                <p className={chrome.surfaceText}>Fetching the latest saved state for this session.</p>
              </div>
              <span className={chrome.statusPillMuted}>Opening</span>
            </div>
            <div className={styles.loadingBeacon} aria-hidden="true" />

            {error ? (
              <div className={styles.errorCard}>
                <p>{error}</p>
              </div>
            ) : null}
          </section>
        ) : showProgressPanel ? (
          <section className={`${chrome.surfaceStrong} ${styles.loadingCard}`}>
            <div className={styles.loadingTop}>
              <div>
                <h2 className={chrome.surfaceTitle}>Building your briefing</h2>
                <p className={chrome.surfaceText}>
                  {session?.detail ?? "Your briefing will appear here as soon as we have content."}
                </p>
              </div>
              <span className={chrome.statusPillMuted}>{clampedProgress}%</span>
            </div>

            <div className={`${chrome.progressTrack} ${styles.progressTrackLive}`}>
              <div className={`${chrome.progressFill} ${styles.progressFillLive}`} style={{ width: `${clampedProgress}%` }} />
            </div>

            <div className={styles.loadingMeta}>
              <span>Usually a few minutes, depending on source length.</span>
              <span>{stageLabel}</span>
            </div>

            <div className={chrome.stepList}>
              {[
                { key: "listen", label: "Listening", hint: "Resolving the source and transcript" },
                { key: "summarize", label: "Drafting", hint: "Pulling out the signal and structure" },
                { key: "finish", label: "Finalizing", hint: "Finishing the briefing and export state" }
              ].map((step, index) => {
                const dotClass =
                  index < activeStepIndex
                    ? chrome.stepDotComplete
                    : index === activeStepIndex
                      ? chrome.stepDotActive
                      : chrome.stepDot;

                return (
                  <div key={step.key} className={chrome.stepRow}>
                    <span className={dotClass} />
                    <div>
                      <p className={chrome.stepLabel}>{step.label}</p>
                      <p className={chrome.stepHint}>{step.hint}</p>
                    </div>
                  </div>
                );
              })}
            </div>

            {error ? (
              <div className={styles.errorCard}>
                <p>{error}</p>
                {showCreditCta ? (
                  <div className={chrome.actionRow}>
                    <Link className={chrome.primaryButton} href="/app/billing#billing-offers">
                      Get more listening time
                    </Link>
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>
        ) : canShowReader ? (
          <section className={chrome.readerLayout}>
            <article className={`${chrome.surfaceStrong} ${chrome.readerMain} ${styles.readerCard}`}>
              <div className={styles.readerHeader}>
                <div>
                  <h2 className={chrome.surfaceTitle}>Briefing</h2>
                  <p className={chrome.surfaceText}>
                    {isReady
                      ? "Final Talven output, ready to read and export."
                      : "The briefing updates live while Talven finishes the draft."}
                  </p>
                </div>
                <span className={isReady ? chrome.statusPillSuccess : chrome.statusPillMuted}>
                  {isReady ? "Final" : "Updating"}
                </span>
              </div>

              {markdownToRender ? (
                <StreamingMarkdown
                  markdown={markdownToRender}
                  isStreaming={!isReady && !isFailed}
                  className={styles.markdown}
                  cursorClassName={styles.streamingCursor}
                />
              ) : (
                <p className={chrome.emptyState}>
                  {isFailed
                    ? "We could not render the briefing. Start a new one when you are ready."
                    : "Your briefing will appear here as soon as Talven has content ready."}
                </p>
              )}
            </article>

            <aside className={chrome.readerSide}>
              <div className={chrome.readerSideCard}>
                <div className={chrome.surfaceHeader}>
                  <div>
                    <h2 className={chrome.surfaceTitle}>Export</h2>
                    <p className={chrome.surfaceText}>Save the finished briefing or return to the workspace.</p>
                  </div>
                </div>
                <div className={chrome.actionRow}>
                  {pdfUrl ? (
                    <a className={chrome.primaryButton} href={pdfUrl} target="_blank" rel="noreferrer">
                      Download PDF
                    </a>
                  ) : (
                    <button
                      className={chrome.primaryButton}
                      type="button"
                      onClick={handlePdfAction}
                      disabled={pdfLoading || !session?.briefing_id}
                    >
                      {primaryPdfActionLabel}
                    </button>
                  )}
                  <Link className={chrome.secondaryButton} href="/app">
                    New briefing
                  </Link>
                </div>
                {pdfError ? <p className={`${chrome.inlineStatus} ${chrome.inlineStatusError}`}>{pdfError}</p> : null}
              </div>

              <div className={chrome.readerSideCard}>
                <div className={chrome.surfaceHeader}>
                  <div>
                    <h2 className={chrome.surfaceTitle}>Status</h2>
                    <p className={chrome.surfaceText}>Current progress and delivery state for this briefing.</p>
                  </div>
                </div>
                <div className={styles.metaList}>
                  <div className={styles.metaRow}>
                    <span className={styles.metaLabel}>State</span>
                    <span className={styles.metaValue}>{stageLabel}</span>
                  </div>
                  <div className={styles.metaRow}>
                    <span className={styles.metaLabel}>Progress</span>
                    <span className={styles.metaValue}>{clampedProgress}%</span>
                  </div>
                </div>
                {session?.detail ? <p className={chrome.subtleText}>{session.detail}</p> : null}
              </div>

              {isFailed ? (
                <div className={styles.errorCard}>Error: {session?.error_message ?? "This briefing failed."}</div>
              ) : null}
              {error ? (
                <div className={styles.errorCard}>
                  <p>{error}</p>
                  {showCreditCta ? (
                    <div className={chrome.actionRow}>
                      <Link className={chrome.primaryButton} href="/app/billing#billing-offers">
                        Get more listening time
                      </Link>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </aside>
          </section>
        ) : (
          <section className={`${chrome.surfaceStrong} ${styles.loadingCard}`}>
            <div className={styles.loadingTop}>
              <div>
                <h2 className={chrome.surfaceTitle}>Preparing your briefing</h2>
                <p className={chrome.surfaceText}>Waiting for the first available draft content.</p>
              </div>
              <span className={chrome.statusPillMuted}>{clampedProgress}%</span>
            </div>

            <div className={`${chrome.progressTrack} ${styles.progressTrackLive}`}>
              <div className={`${chrome.progressFill} ${styles.progressFillLive}`} style={{ width: `${clampedProgress}%` }} />
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

async function sleep(ms: number, signal: AbortSignal) {
  await new Promise<void>((resolve) => {
    const timeoutId = window.setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, ms);
    const abort = () => {
      window.clearTimeout(timeoutId);
      signal.removeEventListener("abort", abort);
      resolve();
    };

    signal.addEventListener("abort", abort, { once: true });
  });
}

function isCreditError(message: string): boolean {
  const normalized = message.toLowerCase();
  return normalized.includes("insufficient credits") || normalized.includes("no remaining credits");
}

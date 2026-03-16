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
import {
  cacheSessionSnapshot,
  evictSessionSnapshot,
  getCachedSessionSnapshot,
  invalidateBriefingsCache
} from "../../../../lib/appDataCache";
import { readSessionStream, type SessionStreamEvent } from "../../sessionStream";
import styles from "../../session.module.css";

const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 5000;
const RECONCILE_INTERVAL_MS = 4000;
const LOADING_SUPPORT_MESSAGES = [
  "Live updates are connected.",
  "Your draft appears here the moment the first section is ready.",
  "You can leave this page and come back later."
] as const;

const STATE_LABELS: Record<BriefingSessionResponse["state"], string> = {
  accepted: "Starting",
  resolving_source: "Checking source",
  reusing_existing: "Checking reuse",
  transcribing: "Listening",
  drafting_briefing: "Drafting",
  finalizing_briefing: "Finalizing",
  ready: "Ready",
  failed: "Needs attention"
};

const STATE_HINTS: Record<BriefingSessionResponse["state"], string> = {
  accepted: "Opening the session and validating the request.",
  resolving_source: "Checking the source, metadata, and reusable assets.",
  reusing_existing: "Looking for transcript and briefing work we can reuse safely.",
  transcribing: "Listening through the source and building the raw transcript.",
  drafting_briefing: "Turning the transcript into a clear, structured briefing.",
  finalizing_briefing: "Finishing the markdown, export state, and delivery details.",
  ready: "Everything is ready to read, export, or revisit later.",
  failed: "Something interrupted the run before delivery completed."
};

type SessionContentDeltaPayload = {
  session_id: string;
  briefing_id: string | null;
  state: BriefingSessionResponse["state"];
  message: string;
  detail: string | null;
  progress: number;
  briefing_has_pdf: boolean;
  markdown_length: number;
  delta: string;
};

type SessionStatusPayload = {
  session_id: string;
  briefing_id: string | null;
  state: BriefingSessionResponse["state"];
  message: string;
  detail: string | null;
  progress: number;
  resolution_type: BriefingSessionResponse["resolution_type"];
  briefing_has_pdf: boolean;
  error_code: string | null;
  error_message: string | null;
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
  const [streamedMarkdown, setStreamedMarkdown] = useState(cachedSnapshot?.briefing_markdown ?? "");
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteConfirming, setDeleteConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(cachedSnapshot?.progress ?? 5);
  const [loadingSupportIndex, setLoadingSupportIndex] = useState(0);
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
    setDeleteLoading(false);
    setDeleteConfirming(false);
    setError(null);

    const prefetchedSnapshot = getCachedSessionSnapshot(sessionId);
    if (prefetchedSnapshot) {
      setSession(prefetchedSnapshot);
      setInitialSnapshotLoaded(true);
      setStreamedMarkdown(prefetchedSnapshot.briefing_markdown ?? "");
      setProgress(prefetchedSnapshot.progress);
      terminalStateRef.current = prefetchedSnapshot.state === "ready" || prefetchedSnapshot.state === "failed";
    } else {
      terminalStateRef.current = false;
      setInitialSnapshotLoaded(false);
      setSession(null);
      setStreamedMarkdown("");
      setProgress(5);
    }

    const abortController = new AbortController();
    const api = createApiClient(accessToken);

    const handleSessionSnapshot = (snapshot: BriefingSessionResponse) => {
      cacheSessionSnapshot(snapshot);
      setSession(snapshot);
      setStreamedMarkdown(snapshot.briefing_markdown ?? "");
      setProgress(snapshot.progress);
      setInitialSnapshotLoaded(true);
      terminalStateRef.current = snapshot.state === "ready" || snapshot.state === "failed";
      lastStreamActivityRef.current = Date.now();
    };

    const handleStatusUpdate = (statusUpdate: SessionStatusPayload) => {
      setSession((current) => {
        if (!current) {
          return current;
        }

        const nextSnapshot: BriefingSessionResponse = {
          ...current,
          briefing_id: statusUpdate.briefing_id ?? current.briefing_id,
          state: statusUpdate.state,
          message: statusUpdate.message,
          detail: statusUpdate.detail,
          progress: statusUpdate.progress,
          resolution_type: statusUpdate.resolution_type,
          briefing_has_pdf: statusUpdate.briefing_has_pdf,
          error_code: statusUpdate.error_code,
          error_message: statusUpdate.error_message,
          briefing_markdown: current.briefing_markdown
        };
        cacheSessionSnapshot(nextSnapshot);
        return nextSnapshot;
      });
      setProgress(statusUpdate.progress);
      setInitialSnapshotLoaded(true);
      terminalStateRef.current = statusUpdate.state === "ready" || statusUpdate.state === "failed";
      lastStreamActivityRef.current = Date.now();
    };

    const handleContentDelta = (contentDelta: SessionContentDeltaPayload) => {
      setStreamedMarkdown((current) => {
        if (contentDelta.markdown_length <= current.length) {
          return current;
        }
        const nextMarkdown = `${current}${contentDelta.delta}`;
        if (nextMarkdown.length !== contentDelta.markdown_length) {
          return nextMarkdown;
        }
        return nextMarkdown;
      });

      setSession((current) => {
        if (!current) {
          return current;
        }

        const currentMarkdown = current.briefing_markdown ?? "";
        const nextMarkdown = `${currentMarkdown}${contentDelta.delta}`;
        const nextSnapshot: BriefingSessionResponse = {
          ...current,
          briefing_id: contentDelta.briefing_id ?? current.briefing_id,
          state: contentDelta.state,
          message: contentDelta.message,
          detail: contentDelta.detail,
          progress: contentDelta.progress,
          briefing_has_pdf: contentDelta.briefing_has_pdf,
          briefing_markdown: nextMarkdown
        };
        cacheSessionSnapshot(nextSnapshot);
        return nextSnapshot;
      });
      setProgress(contentDelta.progress);
      setInitialSnapshotLoaded(true);
      terminalStateRef.current = contentDelta.state === "ready" || contentDelta.state === "failed";
      lastStreamActivityRef.current = Date.now();
    };

    const handleStreamEvent = async (event: SessionStreamEvent<unknown>) => {
      if (!event.data) {
        return;
      }

      lastEventIdRef.current = event.id;
      lastStreamActivityRef.current = Date.now();
      if (event.event === "session.content_delta") {
        handleContentDelta(event.data as SessionContentDeltaPayload);
      } else if (event.event === "session.status") {
        handleStatusUpdate(event.data as SessionStatusPayload);
      } else {
        handleSessionSnapshot(event.data as BriefingSessionResponse);
      }
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
            await readSessionStream<unknown>(response.body, async (event) => {
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

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setLoadingSupportIndex((current) => (current + 1) % LOADING_SUPPORT_MESSAGES.length);
    }, 2600);

    return () => {
      window.clearInterval(intervalId);
    };
  }, []);

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

  const handleDeleteSession = async () => {
    if (!accessToken || !sessionId || deleteLoading) {
      return;
    }

    setDeleteLoading(true);
    setError(null);

    try {
      const response = await fetch(new URL(`/briefing-sessions/${sessionId}`, getApiBaseUrl()).toString(), {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${accessToken}`
        }
      });

      if (!response.ok) {
        let message = "Unable to remove this briefing.";

        try {
          const payload = (await response.json()) as { detail?: string; message?: string; error?: { message?: string } };
          message = payload.error?.message ?? payload.detail ?? payload.message ?? message;
        } catch {
          // Ignore parsing failures and keep the fallback.
        }

        setError(message);
        return;
      }

      evictSessionSnapshot(sessionId);
      invalidateBriefingsCache();
      setDeleteConfirming(false);
      router.replace("/app/briefings");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to remove this briefing.");
    } finally {
      setDeleteLoading(false);
    }
  };

  const isReady = session?.state === "ready";
  const isFailed = session?.state === "failed";
  const isStreaming = Boolean(session && !isReady && !isFailed);
  const rawMarkdown = streamedMarkdown || session?.briefing_markdown || "";
  const markdownToRender = removeGenericBriefingHeading(rawMarkdown);
  const hasMarkdown = Boolean(markdownToRender);
  const clampedProgress = Math.max(0, Math.min(progress, 100));
  const stageLabel = session ? STATE_LABELS[session.state] : "Preparing your briefing";
  const phaseHint = session ? STATE_HINTS[session.state] : "Connecting you to live updates and checking the current session.";
  const headline = isReady
    ? "Your briefing"
    : isFailed
      ? "This briefing failed"
      : hasMarkdown
        ? "Drafting your briefing"
        : "Building your briefing";
  const subhead = isReady
    ? "Read it now, export the PDF, or start another one."
    : isFailed
      ? "The run stopped before the final briefing was delivered."
      : "Talven is working through the source and shaping the briefing.";
  const showProgressPanel = initialSnapshotLoaded && !hasMarkdown && !isReady && !isFailed;
  const showCreditCta = Boolean(error && isCreditError(error));
  const canShowReader = initialSnapshotLoaded && (hasMarkdown || isReady || isFailed);
  const showHeroLivePill = !isReady && !isFailed && !showProgressPanel;
  const primaryPdfActionLabel = pdfLoading
    ? session?.briefing_has_pdf
      ? "Opening PDF..."
      : "Preparing PDF..."
    : session?.briefing_has_pdf || pdfUrl
      ? "Download PDF"
      : "Generate PDF";
  const liveReaderMessage = session ? STATE_HINTS[session.state] : null;

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
            {isFailed ? <span className={chrome.statusPillDanger}>Failed</span> : null}
            {showHeroLivePill ? <span className={`${chrome.statusPillMuted} ${styles.liveStatus}`}>Live</span> : null}
          </div>
        </section>

        {!initialSnapshotLoaded ? (
          <section className={`${chrome.surfaceStrong} ${styles.loadingCard}`}>
            <div className={styles.loadingTop}>
              <div>
                <h2 className={chrome.surfaceTitle}>Opening your briefing</h2>
                <p className={chrome.surfaceText}>Fetching the latest saved state and reconnecting live context.</p>
              </div>
              <span className={chrome.statusPillMuted}>Opening</span>
            </div>
            <div className={styles.loadingBeacon} aria-hidden="true" />
            <p className={chrome.surfaceText}>No reload needed. This page keeps itself in sync.</p>

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
                <h2 className={chrome.surfaceTitle}>{stageLabel}</h2>
                <p className={chrome.surfaceText}>{phaseHint}</p>
              </div>
              <span className={chrome.statusPillMuted}>{clampedProgress}%</span>
            </div>

            <div className={`${chrome.progressTrack} ${styles.progressTrackLive}`}>
              <div className={`${chrome.progressFill} ${styles.progressFillLive}`} style={{ width: `${clampedProgress}%` }} />
            </div>

            <div className={styles.loadingSignalRow}>
              <span className={`${chrome.statusPillMuted} ${styles.liveStatus}`}>Live</span>
              <p className={styles.loadingSignalText}>{LOADING_SUPPORT_MESSAGES[loadingSupportIndex]}</p>
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
              {isStreaming && liveReaderMessage ? (
                <div className={styles.liveReaderBanner}>
                  <div className={styles.liveReaderMeta}>
                    <span className={`${chrome.statusPillMuted} ${styles.liveStatus}`}>{stageLabel}</span>
                    <p className={chrome.surfaceText}>{liveReaderMessage}</p>
                  </div>
                  <span className={styles.liveProgressLabel}>{clampedProgress}%</span>
                </div>
              ) : null}

              {markdownToRender ? (
                <StreamingMarkdown
                  markdown={markdownToRender}
                  isStreaming={isStreaming}
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
                    <h2 className={chrome.surfaceTitle}>Actions</h2>
                    <p className={chrome.surfaceText}>
                      {isReady ? "Export the finished briefing or move on." : "You can leave this page. The live session will keep syncing."}
                    </p>
                  </div>
                </div>
                <div className={styles.actionStack}>
                  <div className={styles.primaryAction}>
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
                  </div>
                  <div className={styles.secondaryActionRow}>
                    <Link className={chrome.secondaryButton} href="/app">
                      New briefing
                    </Link>
                    <Link className={chrome.secondaryButton} href="/app/briefings">
                      Back to briefings
                    </Link>
                  </div>
                </div>
                {pdfError ? <p className={`${chrome.inlineStatus} ${chrome.inlineStatusError}`}>{pdfError}</p> : null}
              </div>

              {isReady ? (
                <div className={`${chrome.readerSideCard} ${styles.dangerCard}`}>
                  <div className={chrome.surfaceHeader}>
                    <div>
                      <h2 className={chrome.surfaceTitle}>Remove from history</h2>
                      <p className={chrome.surfaceText}>
                        This hides the briefing from your library. You can always generate it again from the source.
                      </p>
                    </div>
                  </div>

                  {!deleteConfirming ? (
                    <button
                      className={styles.deleteButton}
                      type="button"
                      onClick={() => {
                        setDeleteConfirming(true);
                        setError(null);
                      }}
                      disabled={deleteLoading}
                    >
                      Delete briefing
                    </button>
                  ) : (
                    <div className={styles.deleteConfirm}>
                      <p className={styles.deletePrompt}>Remove this briefing from your history?</p>
                      <div className={styles.secondaryActionRow}>
                        <button
                          className={chrome.secondaryButton}
                          type="button"
                          onClick={() => {
                            if (!deleteLoading) {
                              setDeleteConfirming(false);
                            }
                          }}
                          disabled={deleteLoading}
                        >
                          Cancel
                        </button>
                        <button className={styles.deleteButton} type="button" onClick={handleDeleteSession} disabled={deleteLoading}>
                          {deleteLoading ? "Removing briefing..." : "Delete briefing"}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ) : null}

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

function removeGenericBriefingHeading(markdown: string): string {
  return markdown.replace(/^#\s+(briefing|podcast briefing|summary)\s*\n+/i, "");
}

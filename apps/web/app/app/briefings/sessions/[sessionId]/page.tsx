"use client";

import Image from "next/image";
import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";

import { createApiClient, getApiBaseUrl, type BriefingSessionResponse } from "@fathom/api-client";

import { AppShellHeader } from "../../../../components/AppShellHeader";
import { StreamingMarkdown } from "../../../../components/StreamingMarkdown";
import { useAppShell } from "../../../../components/AppShellProvider";
import chrome from "../../../../components/app-chrome.module.css";
import { getApiErrorMessage } from "../../../../lib/apiErrors";
import { getAccountLabel } from "../../../../lib/accountLabel";
import { formatExactDuration } from "../../../../lib/format";
import { logger } from "../../../../lib/logger";
import {
  cacheSessionSnapshot,
  evictSessionSnapshot,
  getCachedSessionSnapshot,
  invalidateBriefingsCache
} from "../../../../lib/appDataCache";
import { buildSignInPath } from "../../../../lib/url";
import { readSessionStream, type SessionStreamEvent } from "../../sessionStream";
import {
  briefingSessionReducer,
  createInitialSessionUiState,
  isTerminalSessionState,
  type SessionContentDeltaPayload,
  type SessionStatusPayload
} from "../../sessionState";
import styles from "../../session.module.css";

const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 5000;
const RECONCILE_INTERVAL_MS = 4000;
const READY_MARKDOWN_RECONCILE_ATTEMPTS = 12;
const READY_MARKDOWN_RECONCILE_INTERVAL_MS = 2500;
const STILL_NORMAL_SECONDS = 30;
const LONG_SOURCE_SECONDS = 60;
const LONG_WAIT_SECONDS = 120;
const LEAVE_AND_RETURN_SECONDS = 300;
const POSSIBLY_STUCK_SECONDS = 600;

type BriefingSessionState = BriefingSessionResponse["state"];

const STATE_LABELS: Record<BriefingSessionResponse["state"], string> = {
  accepted: "Starting",
  resolving_source: "Checking source",
  reusing_existing: "Checking library",
  transcribing: "Transcribing audio",
  drafting_briefing: "Writing briefing",
  finalizing_briefing: "Saving briefing",
  ready: "Ready",
  failed: "Needs attention"
};

const STATE_HINTS: Record<BriefingSessionResponse["state"], string> = {
  accepted: "Source received.",
  resolving_source: "Reading the page and looking for usable audio.",
  reusing_existing: "Checking your library before doing new work.",
  transcribing: "Turning audio into text.",
  drafting_briefing: "Shaping the transcript into a reader.",
  finalizing_briefing: "Saving the finished version.",
  ready: "Ready to read, export, or revisit later.",
  failed: "The run stopped before delivery completed."
};

const LIFECYCLE_STEPS: Array<{
  activeText: string;
  beforeText: string;
  completeText: string;
  label: string;
  states: BriefingSessionState[];
}> = [
  {
    activeText: "Reading the source.",
    beforeText: "Waiting for source.",
    completeText: "Source locked.",
    label: "Check source",
    states: ["accepted", "resolving_source", "reusing_existing"]
  },
  {
    activeText: "Listening closely.",
    beforeText: "Waiting for source.",
    completeText: "Transcript ready.",
    label: "Transcribe",
    states: ["transcribing"]
  },
  {
    activeText: "Writing the briefing.",
    beforeText: "Waiting for transcript.",
    completeText: "Briefing written.",
    label: "Write",
    states: ["drafting_briefing"]
  },
  {
    activeText: "Saving the briefing.",
    beforeText: "Waiting for writing.",
    completeText: "Ready to read.",
    label: "Ready",
    states: ["finalizing_briefing", "ready"]
  }
];

type ParsedBriefingSection = {
  id: string;
  level: number;
  title: string;
  content: string;
};

type ParsedBriefing = {
  title: string;
  summary: string;
  takeaways: string;
  articleSections: ParsedBriefingSection[];
  references: ParsedBriefingSection | null;
};

type TakeawayItem = {
  title: string;
  body: string;
};

type BriefingSectionKind = "deepRead" | "standard";

type FailurePresentation = {
  actionHref: string;
  actionLabel: string;
  description: string;
  detail: string;
  title: string;
};

export default function BriefingSessionPage() {
  const router = useRouter();
  const params = useParams();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const sessionId = useMemo(() => params?.sessionId?.toString() ?? "", [params]);
  const signInPath = useMemo(() => {
    const queryString = searchParams.toString();
    return buildSignInPath(`${pathname}${queryString ? `?${queryString}` : ""}`);
  }, [pathname, searchParams]);
  const cachedSnapshot = useMemo(
    () => (sessionId ? getCachedSessionSnapshot(sessionId) : null),
    [sessionId]
  );
  const { accessToken, loading, refreshUsage, remainingSeconds, signOut, user } = useAppShell();
  const [sessionState, dispatchSession] = useReducer(
    briefingSessionReducer,
    cachedSnapshot,
    createInitialSessionUiState
  );
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteConfirming, setDeleteConfirming] = useState(false);
  const [sessionLoadError, setSessionLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [readingProgress, setReadingProgress] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const lastEventIdRef = useRef<string | null>(null);
  const terminalStateRef = useRef(false);
  const lastStreamActivityRef = useRef<number>(Date.now());
  const refreshedUsageSessionRef = useRef<string | null>(null);
  const {
    connectionNotice,
    markdown: streamedMarkdown,
    phase,
    session,
    streamHealth
  } = sessionState;

  useEffect(() => {
    if (session) {
      cacheSessionSnapshot(session);
    }
  }, [session]);

  useEffect(() => {
    if (loading || !sessionId) {
      return;
    }
    if (!accessToken) {
      router.replace(signInPath);
      return;
    }

    lastEventIdRef.current = null;
    lastStreamActivityRef.current = Date.now();
    setPdfUrl(null);
    setPdfError(null);
    setDeleteLoading(false);
    setDeleteConfirming(false);
    setSessionLoadError(null);
    setActionError(null);

    const prefetchedSnapshot = getCachedSessionSnapshot(sessionId);
    dispatchSession({ type: "reset", snapshot: prefetchedSnapshot });
    terminalStateRef.current = prefetchedSnapshot ? isTerminalSessionState(prefetchedSnapshot.state) : false;

    const abortController = new AbortController();
    const api = createApiClient(accessToken);

    const handleSessionSnapshot = (snapshot: BriefingSessionResponse) => {
      dispatchSession({ type: "snapshot", snapshot });
      terminalStateRef.current = terminalStateRef.current || isTerminalSessionState(snapshot.state);
      lastStreamActivityRef.current = Date.now();
      setSessionLoadError(null);
    };

    const handleStatusUpdate = (statusUpdate: SessionStatusPayload) => {
      dispatchSession({ type: "status", status: statusUpdate });
      terminalStateRef.current = terminalStateRef.current || isTerminalSessionState(statusUpdate.state);
      lastStreamActivityRef.current = Date.now();
    };

    const handleContentDelta = (contentDelta: SessionContentDeltaPayload) => {
      dispatchSession({ type: "content_delta", contentDelta });
      terminalStateRef.current = terminalStateRef.current || isTerminalSessionState(contentDelta.state);
      lastStreamActivityRef.current = Date.now();
    };

    const handleStreamEvent = async (event: SessionStreamEvent<unknown>) => {
      if (!event.data) {
        return;
      }

      lastEventIdRef.current = event.id;
      lastStreamActivityRef.current = Date.now();
      dispatchSession({ type: "stream_restored" });
      if (event.event === "session.content_delta") {
        handleContentDelta(event.data as SessionContentDeltaPayload);
      } else if (event.event === "session.status") {
        handleStatusUpdate(event.data as SessionStatusPayload);
      } else {
        handleSessionSnapshot(event.data as BriefingSessionResponse);
      }

      if (event.event === "session.ready" || event.event === "session.failed") {
        const snapshot = event.data as BriefingSessionResponse;
        logger.info("web.session_stream.terminal", {
          session_id: sessionId,
          state: snapshot.state,
          event_id: event.id
        });
      }
    };

    const refreshSessionSnapshot = async (currentSessionId: string, blocking = false) => {
      const handleSnapshotRefreshFailure = (error: unknown) => {
        if (abortController.signal.aborted) {
          return;
        }

        logger.warn("web.session_snapshot.refresh_failed", {
          session_id: currentSessionId,
          blocking,
          error_type: error instanceof Error ? error.name : "UnknownError",
          message: error instanceof Error ? error.message : "Unable to fetch briefing session."
        });
        dispatchSession({ type: "snapshot_load_failed" });
        if (blocking) {
          setSessionLoadError(getApiErrorMessage(error, "Unable to fetch briefing session."));
        } else {
          dispatchSession({
            type: "stream_lost",
            notice: "Connection is catching up. Saved progress remains here."
          });
        }
      };

      try {
        const { data, error: apiError } = await api.GET("/briefing-sessions/{session_id}", {
          params: {
            path: {
              session_id: currentSessionId
            }
          }
        });

        if (abortController.signal.aborted) {
          return null;
        }

        if (apiError) {
          handleSnapshotRefreshFailure(apiError);
          return null;
        }

        if (data) {
          handleSessionSnapshot(data);
          dispatchSession({ type: "stream_restored" });
        }

        return data ?? null;
      } catch (err) {
        handleSnapshotRefreshFailure(err);
        return null;
      }
    };

    const streamSession = async () => {
      let data = prefetchedSnapshot;
      if (!data) {
        data = await refreshSessionSnapshot(sessionId, true);
      } else if (data.state !== "ready" && data.state !== "failed") {
        void refreshSessionSnapshot(sessionId, false);
      }

      if (!data) {
        dispatchSession({ type: "snapshot_load_failed" });
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
              logger.warn("web.session_stream.open_failed", {
                session_id: sessionId,
                status_code: response.status,
                last_event_id: lastEventIdRef.current
              });
              throw new Error(`Unable to open the live session stream (${response.status}).`);
            }

            reconnectDelay = RECONNECT_BASE_DELAY_MS;
            dispatchSession({ type: "stream_restored" });
            logger.info("web.session_stream.opened", {
              session_id: sessionId,
              last_event_id: lastEventIdRef.current
            });
            await readSessionStream<unknown>(response.body, async (event) => {
              await handleStreamEvent(event);
            });

            if (terminalStateRef.current || abortController.signal.aborted) {
              logger.info("web.session_stream.closed", {
                session_id: sessionId,
                reason: terminalStateRef.current ? "terminal_state" : "aborted"
              });
              return;
            }
          } catch (streamError) {
            if (abortController.signal.aborted) {
              logger.info("web.session_stream.closed", {
                session_id: sessionId,
                reason: "aborted"
              });
              return;
            }
            logger.warn("web.session_stream.error", {
              session_id: sessionId,
              error_type: streamError instanceof Error ? streamError.name : "UnknownError",
              message: streamError instanceof Error ? streamError.message : "Unknown stream error"
            });
            dispatchSession({
              type: "stream_lost",
              notice:
                streamError instanceof Error && streamError.message.includes("live session stream")
                  ? "Connection is catching up. Saved progress remains here."
                  : "Live updates paused for a moment. Reconnecting now."
            });
          }

          if (terminalStateRef.current || abortController.signal.aborted) {
            return;
          }

          await sleep(reconnectDelay, abortController.signal);
          logger.info("web.session_stream.reconnecting", {
            session_id: sessionId,
            delay_ms: reconnectDelay
          });
          reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_DELAY_MS);
        }
      } finally {
        if (reconcileTimer !== null) {
          window.clearInterval(reconcileTimer);
        }
      }
    };

    void streamSession().catch((err) => {
      if (abortController.signal.aborted) {
        return;
      }

      logger.warn("web.session_stream.unhandled_error", {
        session_id: sessionId,
        error_type: err instanceof Error ? err.name : "UnknownError",
        message: err instanceof Error ? err.message : "Unexpected session stream error"
      });
      dispatchSession({
        type: "stream_lost",
        notice: "Connection is catching up. Saved progress remains here."
      });
    });

    return () => {
      abortController.abort();
    };
  }, [accessToken, loading, router, sessionId, signInPath]);

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
    setActionError(null);

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

        setActionError(message);
        return;
      }

      evictSessionSnapshot(sessionId);
      invalidateBriefingsCache();
      setDeleteConfirming(false);
      router.replace("/app/briefings");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Unable to remove this briefing.");
    } finally {
      setDeleteLoading(false);
    }
  };

  const isReady = phase === "ready";
  const isFailed = phase === "failed";
  const isStreaming = phase === "streaming";
  const failurePresentation = getFailurePresentation(session, sessionLoadError);
  const rawMarkdown = streamedMarkdown || session?.briefing_markdown || "";
  const markdownToRender = removeGenericBriefingHeading(rawMarkdown);
  const parsedBriefing = useMemo(
    () => parseBriefingMarkdown(markdownToRender, session?.source_title),
    [markdownToRender, session?.source_title]
  );
  const takeawayItems = useMemo(() => parseTakeawayItems(parsedBriefing.takeaways), [parsedBriefing.takeaways]);
  const hasMarkdown = Boolean(markdownToRender);
  const isWaitingForReadyMarkdown = phase === "delivering";
  const stageLabel = isWaitingForReadyMarkdown
    ? "Loading saved briefing"
    : session
      ? STATE_LABELS[session.state]
      : "Opening briefing";
  const phaseHint = isWaitingForReadyMarkdown
    ? "The run is complete. Talven is fetching the saved briefing text."
    : session
      ? STATE_HINTS[session.state]
      : "Opening the reader.";
  const longRunningNotice = getLongRunningNotice(session?.state ?? null, elapsedSeconds);
  const headline = isReady
    ? parsedBriefing.title
    : isFailed
      ? failurePresentation.title
      : hasMarkdown
        ? parsedBriefing.title
        : session?.source_title || "Opening briefing";
  const subhead = isFailed ? failurePresentation.description : "";
  const creditCtaMessage = session?.error_message ?? sessionLoadError;
  const showCreditCta = failurePresentation.actionHref === "/app/billing#billing-offers" || Boolean(creditCtaMessage && isCreditError(creditCtaMessage));
  const canShowReader = phase === "streaming" || phase === "ready" || phase === "failed";
  const showLifecyclePanel = phase !== "ready" && phase !== "failed";
  const lifecycleStepIndex = getLifecycleStepIndex(session?.state ?? null, phase);
  const lifecycleKicker = phase === "loading_session" ? "Reader" : "Briefing in progress";
  const lifecycleTitle = phase === "loading_session" ? "Opening reader" : stageLabel;
  const lifecycleHint =
    phase === "loading_session"
      ? "A live reader is being prepared."
      : phaseHint;
  const lifecycleStatusLabel =
    streamHealth === "reconnecting" ? "Reconnecting" : phase === "loading_session" ? "Opening" : "Live";
  const primaryPdfActionLabel = pdfLoading
    ? session?.briefing_has_pdf
      ? "Opening PDF..."
      : "Preparing PDF..."
    : session?.briefing_has_pdf || pdfUrl
      ? "Download PDF"
      : "Generate PDF";
  const sourceUrl = session?.canonical_source_url ?? session?.submitted_url ?? "";
  const sourceActionLabel = session?.source_type === "youtube" ? "Original video" : "Original source";
  const sourceLabel = session?.source_type === "youtube" ? "YouTube" : "Source";
  const sourceDurationLabel = session?.source_duration_seconds ? formatExactDuration(session.source_duration_seconds) : null;
  const hasTopActions = canShowReader && !isFailed;
  const heroEyebrow = isFailed ? "Briefing failed" : !isReady ? stageLabel : "";
  const showHeroTopline = Boolean(heroEyebrow || isFailed);
  const navigationSections = [
    parsedBriefing.summary ? { id: "briefing-summary", label: "Summary" } : null,
    parsedBriefing.takeaways ? { id: "briefing-takeaways", label: "Takeaways" } : null,
    ...parsedBriefing.articleSections.map((section) => ({ id: section.id, label: section.title })),
    parsedBriefing.references ? { id: parsedBriefing.references.id, label: "References" } : null
  ].filter((item): item is { id: string; label: string } => Boolean(item));
  const mobileNavigationSections = navigationSections.slice(0, 3);

  useEffect(() => {
    if (!accessToken || !sessionId || phase !== "delivering") {
      return undefined;
    }

    let attempts = 0;
    let cancelled = false;
    const api = createApiClient(accessToken);

    const reconcileReadyMarkdown = async () => {
      attempts += 1;
      const { data, error: apiError } = await api.GET("/briefing-sessions/{session_id}", {
        params: {
          path: {
            session_id: sessionId
          }
        }
      });

      if (cancelled) {
        return;
      }

      if (apiError) {
        logger.warn("web.session.ready_markdown_reconcile_failed", {
          session_id: sessionId,
          attempt: attempts
        });
        return;
      }

      if (data) {
        dispatchSession({ type: "snapshot", snapshot: data });
      }
    };

    const intervalId = window.setInterval(() => {
      if (attempts >= READY_MARKDOWN_RECONCILE_ATTEMPTS) {
        window.clearInterval(intervalId);
        return;
      }

      void reconcileReadyMarkdown();
    }, READY_MARKDOWN_RECONCILE_INTERVAL_MS);

    void reconcileReadyMarkdown();

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [accessToken, phase, sessionId]);

  useEffect(() => {
    if (phase !== "ready" || !session?.session_id || refreshedUsageSessionRef.current === session.session_id) {
      return;
    }

    refreshedUsageSessionRef.current = session.session_id;
    void refreshUsage();
  }, [phase, refreshUsage, session?.session_id]);

  useEffect(() => {
    if (!showLifecyclePanel) {
      setElapsedSeconds(0);
      return undefined;
    }

    const startedAt = Date.now();
    setElapsedSeconds(0);
    const intervalId = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [sessionId, showLifecyclePanel]);

  useEffect(() => {
    if (!canShowReader) {
      setReadingProgress(0);
      return undefined;
    }

    const updateReadingProgress = () => {
      const scrollableHeight = document.documentElement.scrollHeight - window.innerHeight;
      if (scrollableHeight <= 0) {
        setReadingProgress(100);
        return;
      }

      setReadingProgress(Math.max(0, Math.min(100, Math.round((window.scrollY / scrollableHeight) * 100))));
    };

    updateReadingProgress();
    window.addEventListener("scroll", updateReadingProgress, { passive: true });
    window.addEventListener("resize", updateReadingProgress);

    return () => {
      window.removeEventListener("scroll", updateReadingProgress);
      window.removeEventListener("resize", updateReadingProgress);
    };
  }, [canShowReader, sessionId]);

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader
        active="briefings"
        remainingSeconds={remainingSeconds}
        accountLabel={getAccountLabel(user)}
        onSignOut={signOut}
      />

      <main id="main-content" className={chrome.mainFrame}>
        <section className={`${chrome.heroBlock} ${styles.sessionHero}`}>
          <div className={styles.sessionHeroGrid}>
            <div className={styles.heroSourceMedia}>
              {session?.source_thumbnail_url ? (
                <div className={styles.heroThumbnailFrame}>
                  <Image className={styles.heroThumbnail} src={session.source_thumbnail_url} alt="" fill sizes="160px" priority />
                </div>
              ) : (
                <div className={styles.heroThumbnailFrame}>
                  <div className={styles.sourceThumbnailFallback}>
                    <span>{sourceLabel}</span>
                  </div>
                </div>
              )}
            </div>

            <div className={styles.heroCopy}>
              {showHeroTopline ? (
                <div className={styles.heroTopline}>
                  {heroEyebrow ? <p className={chrome.heroEyebrow}>{heroEyebrow}</p> : null}
                  <div className={chrome.heroMeta}>
                    {isFailed ? <span className={chrome.statusPillDanger}>Failed</span> : null}
                  </div>
                </div>
              ) : null}
              <h1 className={styles.sessionTitle}>{headline}</h1>
              <div className={styles.sourceMetaLine}>
                {session?.source_author ? <span>By {session.source_author}</span> : null}
                {sourceDurationLabel ? <span>{sourceDurationLabel}</span> : null}
                {session?.source_title && parsedBriefing.title !== session.source_title ? <span>{session.source_title}</span> : null}
              </div>
              {subhead ? <p className={styles.sessionDeck}>{subhead}</p> : null}
            </div>
          </div>

          {showLifecyclePanel ? (
            <div className={styles.lifecyclePanel} aria-live="polite">
              <div className={styles.lifecycleHeader}>
                <div>
                  <p className={styles.lifecycleKicker}>{lifecycleKicker}</p>
                  <h2>{lifecycleTitle}</h2>
                  <p>{lifecycleHint}</p>
                </div>
                <span
                  className={`${chrome.statusPillMuted} ${
                    streamHealth === "reconnecting" ? styles.lifecycleWarningPill : styles.liveStatus
                  }`}
                >
                  {lifecycleStatusLabel}
                </span>
              </div>

              <div className={styles.lifecycleSteps} aria-label="Briefing progress">
                {LIFECYCLE_STEPS.map((step, index) => (
                  <div
                    className={getLifecycleStepClassName(index, lifecycleStepIndex)}
                    key={step.label}
                    aria-current={index === lifecycleStepIndex ? "step" : undefined}
                  >
                    <span aria-hidden="true" />
                    <div>
                      <p>{step.label}</p>
                      <small>
                        {getLifecycleStepDescription({
                          index,
                          phase,
                          state: session?.state ?? null,
                          step,
                          activeIndex: lifecycleStepIndex
                        })}
                        {index === lifecycleStepIndex ? <span className={styles.lifecycleEllipsis} aria-hidden="true" /> : null}
                      </small>
                    </div>
                  </div>
                ))}
              </div>

              {longRunningNotice ? (
                <div className={styles.statusNoticeCard}>
                  <p>{longRunningNotice}</p>
                </div>
              ) : null}

              {connectionNotice ? (
                <div className={styles.connectionCard}>
                  <p>{connectionNotice}</p>
                </div>
              ) : null}

              {sessionLoadError ? (
                <div className={styles.errorCard}>
                  <p>{sessionLoadError}</p>
                  {showCreditCta ? (
                    <div className={chrome.actionRow}>
                      <Link className={chrome.primaryButton} href="/app/billing#billing-offers">
                        Get more listening time
                      </Link>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}

          {hasTopActions ? (
            <div className={styles.heroActionBar}>
              {pdfUrl ? (
                <a className={`${chrome.primaryButton} ${styles.heroPdfAction}`} href={pdfUrl} target="_blank" rel="noreferrer">
                  Download PDF
                </a>
              ) : (
                <button
                  className={`${chrome.primaryButton} ${styles.heroPdfAction}`}
                  type="button"
                  onClick={handlePdfAction}
                  disabled={pdfLoading || !session?.briefing_id}
                >
                  {primaryPdfActionLabel}
                </button>
              )}
              <div className={styles.heroUtilityLinks}>
                {sourceUrl ? (
                  <a className={styles.textActionLink} href={sourceUrl} target="_blank" rel="noreferrer">
                    {sourceActionLabel}
                  </a>
                ) : null}
                <Link className={`${styles.textActionLink} ${styles.newBriefingLink}`} href="/app">
                  New briefing
                </Link>
              </div>
            </div>
          ) : null}
          {pdfError ? <p className={`${chrome.inlineStatus} ${chrome.inlineStatusError}`}>{pdfError}</p> : null}
        </section>

        {canShowReader ? (
          <section className={styles.briefingLayout}>
            {mobileNavigationSections.length ? (
              <nav className={styles.mobileReaderBar} aria-label="Reader shortcuts">
                <div className={styles.mobileReaderLinks}>
                  {mobileNavigationSections.map((section) => (
                    <a href={`#${section.id}`} key={section.id}>
                      {getMobileSectionLabel(section.label)}
                    </a>
                  ))}
                </div>
                {isReady ? (
                  pdfUrl ? (
                    <a className={styles.mobileReaderAction} href={pdfUrl} target="_blank" rel="noreferrer">
                      PDF
                    </a>
                  ) : (
                    <button
                      className={styles.mobileReaderAction}
                      type="button"
                      onClick={handlePdfAction}
                      disabled={pdfLoading || !session?.briefing_id}
                    >
                      {pdfLoading ? "PDF..." : "PDF"}
                    </button>
                  )
                ) : null}
              </nav>
            ) : null}

            <article className={styles.briefingReader}>
              {connectionNotice && !showLifecyclePanel ? (
                <div className={styles.connectionCard}>
                  <p>{connectionNotice}</p>
                </div>
              ) : null}

              {parsedBriefing.summary ? (
                <section className={`${chrome.surfaceStrong} ${styles.summaryPanel}`} id="briefing-summary">
                  <p className={styles.sectionKicker}>Brief in 30 seconds</p>
                  <StreamingMarkdown
                    markdown={emphasizeFirstSentence(parsedBriefing.summary)}
                    className={`${styles.markdown} ${styles.summaryMarkdown}`}
                  />
                </section>
              ) : null}

              {parsedBriefing.takeaways ? (
                <section className={`${chrome.surface} ${styles.takeawayPanel}`} id="briefing-takeaways">
                  <div className={styles.sectionHeader}>
                    <p className={styles.sectionKicker}>What matters</p>
                    <h2 className={styles.sectionTitle}>Key takeaways</h2>
                  </div>
                  {takeawayItems.length > 1 ? (
                    <ol className={styles.takeawayGrid}>
                      {takeawayItems.map((takeaway, index) => (
                        <li className={styles.takeawayCard} key={`${takeaway.title}-${index}`}>
                          <h3>{takeaway.title}</h3>
                          <p>{takeaway.body}</p>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <StreamingMarkdown markdown={parsedBriefing.takeaways} className={`${styles.markdown} ${styles.takeawayMarkdown}`} />
                  )}
                </section>
              ) : null}

              {parsedBriefing.articleSections.length ? (
                <div className={styles.articleStack}>
                  {parsedBriefing.articleSections.map((section) => (
                    <BriefingContentSection section={section} key={section.id} />
                  ))}
                </div>
              ) : markdownToRender && !parsedBriefing.summary && !parsedBriefing.takeaways ? (
                <section className={`${chrome.surface} ${styles.articleSection}`}>
                  <StreamingMarkdown
                    markdown={markdownToRender}
                    isStreaming={isStreaming}
                    className={styles.markdown}
                    cursorClassName={styles.streamingCursor}
                  />
                </section>
              ) : (
                <p className={chrome.emptyState}>
                  {isFailed
                    ? "We could not render the briefing. Start a new one when you are ready."
                    : "Your briefing will appear here as soon as Talven has content ready."}
                </p>
              )}

              {parsedBriefing.references ? (
                <section className={`${chrome.surfaceMuted} ${styles.referenceSection}`} id={parsedBriefing.references.id}>
                  <details>
                    <summary>Sources and references</summary>
                    <StreamingMarkdown markdown={parsedBriefing.references.content} className={styles.markdown} />
                  </details>
                </section>
              ) : null}
            </article>

            <aside className={styles.briefingSide}>
              {navigationSections.length > 2 ? (
                <nav className={`${chrome.readerSideCard} ${styles.contentsCard}`} aria-label="Briefing sections">
                  <div className={styles.contentsHeader}>
                    <h2 className={chrome.surfaceTitle}>Contents</h2>
                    <span>{readingProgress}% read</span>
                  </div>
                  <div className={styles.contentsProgressTrack} aria-hidden="true">
                    <div className={styles.contentsProgressFill} style={{ width: `${readingProgress}%` }} />
                  </div>
                  <div className={styles.contentsList}>
                    {navigationSections.map((section) => (
                      <a href={`#${section.id}`} key={section.id}>
                        {section.label}
                      </a>
                    ))}
                  </div>
                </nav>
              ) : null}

              {session ? (
                <section className={`${chrome.readerSideCard} ${styles.sourceCard}`} aria-label="Source">
                  <p className={styles.sideKicker}>Source</p>
                  <div className={styles.sourceHeader}>
                    <div className={styles.sourceMedia}>
                      <div className={styles.sourceThumbnailFrame}>
                        {session.source_thumbnail_url ? (
                          <Image
                            className={styles.sourceThumbnail}
                            src={session.source_thumbnail_url}
                            alt=""
                            fill
                            sizes="112px"
                          />
                        ) : (
                          <div className={styles.sourceThumbnailFallback}>
                            <span>{sourceLabel}</span>
                          </div>
                        )}
                      </div>
                    </div>
                    <div className={styles.sourceBody}>
                      <div className={styles.sourceSummary}>
                        <h2 className={styles.sourceTitle}>{session.source_title || headline}</h2>
                        <div className={styles.sourceMeta}>
                          {session.source_author ? <span>{session.source_author}</span> : null}
                          {sourceDurationLabel ? <span>{sourceDurationLabel}</span> : null}
                        </div>
                      </div>
                      {sourceUrl ? (
                        <a className={styles.sourceCardLink} href={sourceUrl} target="_blank" rel="noreferrer">
                          Open original
                        </a>
                      ) : null}
                    </div>
                  </div>
                </section>
              ) : null}

              <div className={styles.desktopActionCard}>
                <Link className={styles.textActionLink} href="/app/briefings">
                  Back to briefings
                </Link>
                <Link className={styles.textActionLink} href="/app">
                  New briefing
                </Link>
                {isReady && !deleteConfirming ? (
                  <button
                    className={`${styles.textActionLink} ${styles.removeTextButton}`}
                    type="button"
                    onClick={() => {
                      setDeleteConfirming(true);
                      setActionError(null);
                    }}
                    disabled={deleteLoading}
                  >
                    Remove briefing
                  </button>
                ) : null}
                {isReady && deleteConfirming ? (
                  <div className={styles.sidebarDeleteConfirm}>
                    <p>Remove this briefing?</p>
                    <div className={styles.sidebarDeleteActions}>
                      <button
                        className={styles.textActionLink}
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
                      <button
                        className={`${styles.textActionLink} ${styles.removeTextButton}`}
                        type="button"
                        onClick={handleDeleteSession}
                        disabled={deleteLoading}
                      >
                        {deleteLoading ? "Removing..." : "Remove"}
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>

              {isFailed ? (
                <div className={styles.errorCard}>
                  <p>{failurePresentation.detail}</p>
                  {failurePresentation.actionHref ? (
                    <div className={chrome.actionRow}>
                      <Link className={chrome.primaryButton} href={failurePresentation.actionHref}>
                        {failurePresentation.actionLabel}
                      </Link>
                    </div>
                  ) : null}
                </div>
              ) : null}
              {actionError ? (
                <div className={styles.errorCard}>
                  <p>{actionError}</p>
                </div>
              ) : null}
            </aside>

            <footer className={styles.briefingFooter}>
              <div className={styles.footerPrimaryRow}>
                {isReady ? (
                  pdfUrl ? (
                    <a className={styles.footerPdfAction} href={pdfUrl} target="_blank" rel="noreferrer">
                      Download PDF
                    </a>
                  ) : (
                    <button
                      className={styles.footerPdfAction}
                      type="button"
                      onClick={handlePdfAction}
                      disabled={pdfLoading || !session?.briefing_id}
                    >
                      {primaryPdfActionLabel}
                    </button>
                  )
                ) : null}
              </div>
              <div className={styles.footerNavigationRow}>
                <Link className={styles.textActionLink} href="/app/briefings">
                  Back to briefings
                </Link>
                <Link className={styles.textActionLink} href="/app">
                  New briefing
                </Link>
              </div>
              {isReady && !deleteConfirming ? (
                <div className={styles.footerDangerRow}>
                  <button
                    className={`${styles.textActionLink} ${styles.removeTextButton}`}
                    type="button"
                    onClick={() => {
                      setDeleteConfirming(true);
                      setActionError(null);
                    }}
                    disabled={deleteLoading}
                  >
                    Remove briefing
                  </button>
                </div>
              ) : null}
              {isReady && deleteConfirming ? (
                <div className={styles.footerDeleteConfirm}>
                  <span>Remove this briefing from your library?</span>
                  <button
                    className={styles.textActionLink}
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
                  <button className={`${styles.textActionLink} ${styles.removeTextButton}`} type="button" onClick={handleDeleteSession} disabled={deleteLoading}>
                    {deleteLoading ? "Removing..." : "Remove"}
                  </button>
                </div>
              ) : null}
            </footer>
          </section>
        ) : null}
      </main>
    </div>
  );
}

function BriefingContentSection({ section }: { section: ParsedBriefingSection }) {
  const sectionKind = getSectionKind(section.title);
  const sectionClassName = [
    chrome.surface,
    styles.articleSection,
    sectionKind === "deepRead" ? styles.deepReadSection : "",
  ]
    .filter(Boolean)
    .join(" ");
  const markdownClassName = [
    styles.markdown,
    sectionKind === "deepRead" ? styles.deepReadMarkdown : ""
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <section className={sectionClassName} id={section.id}>
      <h2 className={styles.articleSectionTitle}>{getSectionDisplayTitle(section.title, sectionKind)}</h2>
      <StreamingMarkdown markdown={section.content} className={markdownClassName} />
    </section>
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

function parseBriefingMarkdown(markdown: string, fallbackTitle?: string | null): ParsedBriefing {
  const cleanedMarkdown = normalizeBriefingMarkdown(markdown).trim();
  const sections = splitMarkdownSections(cleanedMarkdown);
  const titleSection = sections.find((section) => section.level === 1 && !isGenericTitle(section.title));
  const title = titleSection?.title || fallbackTitle || "Untitled briefing";
  const summarySection = sections.find((section) => isSummaryHeading(section.title));
  const takeawaysSection = sections.find((section) => isTakeawaysHeading(section.title));
  const referencesSection = sections.find((section) => isReferencesHeading(section.title)) ?? null;
  const bodySections = sections.filter(
    (section) =>
      section !== titleSection &&
      section !== summarySection &&
      section !== takeawaysSection &&
      section !== referencesSection &&
      section.content.trim()
  );
  const hasRecognizedStructure = Boolean(titleSection || summarySection || takeawaysSection || referencesSection || bodySections.length);

  const articleSections = bodySections.length
    ? bodySections.map((section) => ({
        ...section,
        title: humanizeSectionTitle(section.title)
      }))
    : cleanedMarkdown && !hasRecognizedStructure
      ? [
          {
            id: "briefing-notes",
            level: 2,
            title: "Briefing notes",
            content: cleanedMarkdown
          }
        ]
      : [];

  return {
    title,
    summary: summarySection?.content.trim() ?? "",
    takeaways: takeawaysSection?.content.trim() ?? "",
    articleSections,
    references: referencesSection
      ? {
          ...referencesSection,
          title: humanizeSectionTitle(referencesSection.title)
        }
      : null
  };
}

function splitMarkdownSections(markdown: string): ParsedBriefingSection[] {
  if (!markdown.trim()) {
    return [];
  }

  const lines = markdown.split(/\r?\n/);
  const sections: Array<ParsedBriefingSection & { contentLines: string[] }> = [];
  let current: (ParsedBriefingSection & { contentLines: string[] }) | null = null;
  const prefaceLines: string[] = [];

  for (const line of lines) {
    const headingMatch = /^(#{1,2})\s+(.+?)\s*#*\s*$/.exec(line);
    if (!headingMatch) {
      if (current) {
        current.contentLines.push(line);
      } else {
        prefaceLines.push(line);
      }
      continue;
    }

    if (current) {
      current.content = current.contentLines.join("\n").trim();
      sections.push(current);
    }

    const title = cleanInlineMarkdown(headingMatch[2]);
    current = {
      id: getSectionId(title, sections.length),
      level: headingMatch[1].length,
      title,
      content: "",
      contentLines: []
    };
  }

  if (current) {
    current.content = current.contentLines.join("\n").trim();
    sections.push(current);
  }

  const preface = prefaceLines.join("\n").trim();
  if (preface) {
    sections.unshift({
      id: "briefing-overview",
      level: 2,
      title: "Overview",
      content: preface,
      contentLines: []
    });
  }

  return sections.map(({ contentLines: _contentLines, ...section }) => section);
}

function normalizeBriefingMarkdown(markdown: string): string {
  const withoutDecorations = markdown
    .replace(/^(\s*[-*+]\s*)(?:[\u2705\u26a0\ufe0f]|\u{1f4a1})\s*/gmu, "$1")
    .replace(/^((?:[\u2705\u26a0\ufe0f]|\u{1f4a1})\s*)+/gmu, "");
  return normalizeLooseSectionHeadings(withoutDecorations);
}

function normalizeLooseSectionHeadings(markdown: string): string {
  const lines = markdown.split(/\r?\n/);
  const normalizedLines: string[] = [];
  let sawHeading = false;
  let sawKnownSection = false;

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = cleanInlineMarkdown(line);

    if (/^#{1,6}\s+/.test(line.trim())) {
      sawHeading = true;
      normalizedLines.push(line);
      continue;
    }

    const knownSectionTitle = getKnownBriefingSectionTitle(trimmed);
    if (knownSectionTitle) {
      sawHeading = true;
      sawKnownSection = true;
      normalizedLines.push(`## ${knownSectionTitle}`);
      continue;
    }

    const isFirstMeaningfulLine = !sawHeading && trimmed && !line.trim().startsWith("-") && !line.trim().startsWith("*");
    const nextKnownSection = getKnownBriefingSectionTitle(getNextMeaningfulLine(lines, index));
    if (isFirstMeaningfulLine && nextKnownSection) {
      sawHeading = true;
      normalizedLines.push(`# ${trimmed}`);
      continue;
    }

    normalizedLines.push(line);
  }

  if (!sawKnownSection) {
    return markdown;
  }

  return normalizedLines.join("\n");
}

function getNextMeaningfulLine(lines: string[], currentIndex: number): string {
  for (let index = currentIndex + 1; index < lines.length; index += 1) {
    const nextLine = cleanInlineMarkdown(lines[index]);
    if (nextLine) {
      return nextLine;
    }
  }
  return "";
}

function getKnownBriefingSectionTitle(value: string): string | null {
  const normalized = value.replace(/:$/, "").toLowerCase();
  if (/^brief in (?:30|thirty) seconds$/.test(normalized) || normalized === "brief") {
    return "Brief in 30 seconds";
  }
  if (/^key takeaways?$/.test(normalized) || normalized === "what matters") {
    return "Key Takeaways";
  }
  if (/^(?:detailed|deep|full) briefing$/.test(normalized) || normalized === "deeper read") {
    return "Detailed Briefing";
  }
  if (/^highlights?(?: & | and )quotes?$/.test(normalized)) {
    return "Highlights & Quotes";
  }
  if (/^action items?$/.test(normalized)) {
    return "Action Items";
  }
  if (/^next steps?$/.test(normalized)) {
    return "Next Steps";
  }
  if (/^open questions?$/.test(normalized)) {
    return "Open Questions";
  }
  if (/^(?:references|sources)$/.test(normalized)) {
    return "References";
  }
  return null;
}

function cleanInlineMarkdown(value: string): string {
  return value
    .replace(/[*_`~]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function humanizeSectionTitle(value: string): string {
  if (/^tl;?dr$/i.test(value.trim())) {
    return "Summary";
  }
  return value;
}

function getSectionKind(title: string): BriefingSectionKind {
  if (/detailed|briefing|summary/i.test(title)) {
    return "deepRead";
  }
  return "standard";
}

function getSectionDisplayTitle(title: string, kind: BriefingSectionKind): string {
  if (kind === "deepRead" && /detailed/i.test(title)) {
    return "Deeper read";
  }
  return title;
}

function getMobileSectionLabel(label: string): string {
  if (/references?|sources?/i.test(label)) {
    return "Sources";
  }
  if (/detailed|deeper/i.test(label)) {
    return "Details";
  }
  if (label.length > 14) {
    return "Section";
  }
  return label;
}

function getLongRunningNotice(state: BriefingSessionResponse["state"] | null, elapsedSeconds: number): string | null {
  if (!state || state === "ready" || state === "failed" || elapsedSeconds < STILL_NORMAL_SECONDS) {
    return null;
  }

  if (elapsedSeconds >= POSSIBLY_STUCK_SECONDS) {
    return "This is taking much longer than expected. You can leave and return from Briefings, or try again later if it never finishes.";
  }

  if (elapsedSeconds >= LEAVE_AND_RETURN_SECONDS) {
    return "Still working. This is longer than normal, but longer sources can take several minutes. You can return from Briefings.";
  }

  if (elapsedSeconds >= LONG_WAIT_SECONDS) {
    return "Still working. This is taking a little longer than usual, especially if the source is long.";
  }

  if (elapsedSeconds >= LONG_SOURCE_SECONDS) {
    return "Still moving. Longer sources can take a minute or two before the briefing starts to appear.";
  }

  if (elapsedSeconds >= STILL_NORMAL_SECONDS) {
    return "Still working through the source.";
  }

  return null;
}

function getFailurePresentation(
  session: BriefingSessionResponse | null,
  sessionLoadError: string | null
): FailurePresentation {
  const code = session?.error_code ?? "";
  const rawMessage = session?.error_message ?? sessionLoadError ?? "";
  const normalizedMessage = rawMessage.toLowerCase();

  if (isCreditError(rawMessage)) {
    return {
      actionHref: "/app/billing#billing-offers",
      actionLabel: "Get more listening time",
      title: "More listening time needed",
      description: "This source needs more minutes than are currently available.",
      detail: "Add more listening time, then start the briefing again."
    };
  }

  if (
    code === "invalid_request" ||
    code === "invalid_job_payload" ||
    normalizedMessage.includes("unsupported") ||
    normalizedMessage.includes("no audio streams") ||
    normalizedMessage.includes("youtube downloader") ||
    normalizedMessage.includes("download audio")
  ) {
    return {
      actionHref: "/app",
      actionLabel: "Try another source",
      title: "Source not supported",
      description: "Talven could not read usable audio from this link.",
      detail: "Try a public YouTube or podcast URL. Private, unavailable, or audio-free sources cannot be briefed yet."
    };
  }

  if (
    normalizedMessage.includes("groq") ||
    normalizedMessage.includes("transcript") ||
    normalizedMessage.includes("transcription") ||
    normalizedMessage.includes("empty transcript")
  ) {
    return {
      actionHref: "/app",
      actionLabel: "Start another briefing",
      title: "Transcript failed",
      description: "The source opened, but the audio could not be transcribed.",
      detail: "This is usually caused by unavailable audio, provider trouble, or an empty transcript. Try again in a moment or use another source."
    };
  }

  if (
    normalizedMessage.includes("openrouter") ||
    normalizedMessage.includes("summary") ||
    normalizedMessage.includes("summar")
  ) {
    return {
      actionHref: "/app",
      actionLabel: "Start another briefing",
      title: "Briefing failed",
      description: "The transcript was available, but the written briefing could not be completed.",
      detail: "The summarizer did not return a usable briefing. Try again in a moment; if it repeats, this source may need a shorter or cleaner input."
    };
  }

  if (code === "max_attempts_exceeded") {
    return {
      actionHref: "/app",
      actionLabel: "Start another briefing",
      title: "Briefing took too long",
      description: "Talven retried the job but could not finish it.",
      detail: "This can happen with provider timeouts or unusually difficult sources. Try again later or use another source."
    };
  }

  if (code === "configuration_error") {
    return {
      actionHref: "/app",
      actionLabel: "Back to workspace",
      title: "Service configuration issue",
      description: "Talven could not complete this briefing because a required service is unavailable.",
      detail: "This needs an operator fix. The source was not the problem."
    };
  }

  return {
    actionHref: "/app",
    actionLabel: "Start another briefing",
    title: "Briefing stopped",
    description: "Something interrupted the run before the final briefing was delivered.",
    detail: rawMessage || "The briefing could not be completed. Try again in a moment or use another source."
  };
}

function getLifecycleStepIndex(
  state: BriefingSessionResponse["state"] | null,
  phase: string
): number {
  if (phase === "loading_session" || !state) {
    return 0;
  }
  if (phase === "delivering") {
    return LIFECYCLE_STEPS.length - 1;
  }
  const stepIndex = LIFECYCLE_STEPS.findIndex((step) => step.states.includes(state));
  return Math.max(0, stepIndex);
}

function getLifecycleStepClassName(index: number, activeIndex: number): string {
  return [
    styles.lifecycleStep,
    index < activeIndex ? styles.lifecycleStepComplete : "",
    index === activeIndex ? styles.lifecycleStepActive : ""
  ]
    .filter(Boolean)
    .join(" ");
}

function getLifecycleStepDescription({
  activeIndex,
  index,
  phase,
  state,
  step
}: {
  activeIndex: number;
  index: number;
  phase: string;
  state: BriefingSessionResponse["state"] | null;
  step: (typeof LIFECYCLE_STEPS)[number];
}): string {
  if (index < activeIndex) {
    return step.completeText;
  }
  if (index > activeIndex) {
    return step.beforeText;
  }
  if (phase === "loading_session") {
    return "Opening the reader.";
  }
  if (phase === "delivering") {
    return "Ready in a moment.";
  }
  if (state === "accepted") {
    return "Warming up.";
  }
  if (state === "resolving_source") {
    return "Finding the signal.";
  }
  if (state === "reusing_existing") {
    return "Checking memory.";
  }
  if (state === "transcribing") {
    return step.activeText;
  }
  if (state === "drafting_briefing") {
    return step.activeText;
  }
  if (state === "finalizing_briefing") {
    return step.activeText;
  }
  return step.activeText;
}

function emphasizeFirstSentence(markdown: string): string {
  const trimmed = markdown.trim();
  if (!trimmed || trimmed.startsWith("**") || trimmed.startsWith("#") || trimmed.includes("\n- ")) {
    return markdown;
  }

  const sentenceMatch = /^(.+?[.!?])(\s+.+)$/s.exec(trimmed);
  if (!sentenceMatch) {
    return markdown;
  }

  return `**${sentenceMatch[1]}**${sentenceMatch[2]}`;
}

function parseTakeawayItems(markdown: string): TakeawayItem[] {
  const items: TakeawayItem[] = [];
  const pattern = /(?:^|\n)\s*(?:[-*+]\s*)?\*\*(.+?)\*\*\s*:?\s*([\s\S]*?)(?=\n\s*(?:[-*+]\s*)?\*\*.+?\*\*\s*:|$)/g;

  for (const match of markdown.matchAll(pattern)) {
    const title = cleanInlineMarkdown(match[1]);
    const body = cleanInlineMarkdown(match[2].replace(/^[-*+]\s*/, ""));

    if (title && body) {
      items.push({ title, body });
    }
  }

  return items;
}

function getSectionId(title: string, index: number): string {
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .slice(0, 48);

  return `briefing-${slug || "section"}-${index}`;
}

function isGenericTitle(title: string): boolean {
  return /^(briefing|podcast briefing|summary)$/i.test(title.trim());
}

function isSummaryHeading(title: string): boolean {
  const normalized = title.toLowerCase().replace(/[^\w]+/g, "");
  return normalized === "tldr" || normalized === "summary" || normalized === "briefin30seconds";
}

function isTakeawaysHeading(title: string): boolean {
  return /takeaways?/i.test(title);
}

function isReferencesHeading(title: string): boolean {
  return /references?|sources?/i.test(title);
}

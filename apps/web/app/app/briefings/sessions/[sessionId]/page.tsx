"use client";

import Image from "next/image";
import { useEffect, useMemo, useRef, useState } from "react";
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
  source_title: string;
  source_author: string | null;
  source_duration_seconds: number | null;
  source_thumbnail_url: string | null;
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
  source_title: string;
  source_author: string | null;
  source_duration_seconds: number | null;
  source_thumbnail_url: string | null;
  briefing_has_pdf: boolean;
  error_code: string | null;
  error_message: string | null;
};

type StreamHealth = "live" | "reconnecting";

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

type BriefingSectionKind = "deepRead" | "standard";

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
  const { accessToken, loading, remainingSeconds, signOut, user } = useAppShell();
  const [session, setSession] = useState<BriefingSessionResponse | null>(cachedSnapshot);
  const [initialSnapshotLoaded, setInitialSnapshotLoaded] = useState(Boolean(cachedSnapshot));
  const [streamedMarkdown, setStreamedMarkdown] = useState(cachedSnapshot?.briefing_markdown ?? "");
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteConfirming, setDeleteConfirming] = useState(false);
  const [sessionLoadError, setSessionLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [connectionNotice, setConnectionNotice] = useState<string | null>(null);
  const [streamHealth, setStreamHealth] = useState<StreamHealth>("live");
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
    setConnectionNotice(null);
    setStreamHealth("live");

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
      setSessionLoadError(null);
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
          source_title: statusUpdate.source_title,
          source_author: statusUpdate.source_author,
          source_duration_seconds: statusUpdate.source_duration_seconds,
          source_thumbnail_url: statusUpdate.source_thumbnail_url,
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
          source_title: contentDelta.source_title,
          source_author: contentDelta.source_author,
          source_duration_seconds: contentDelta.source_duration_seconds,
          source_thumbnail_url: contentDelta.source_thumbnail_url,
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
      setStreamHealth("live");
      setConnectionNotice(null);
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
      const { data, error: apiError } = await api.GET("/briefing-sessions/{session_id}", {
        params: {
          path: {
            session_id: currentSessionId
          }
        }
      });

      if (apiError) {
        setInitialSnapshotLoaded(true);
        if (blocking) {
          setSessionLoadError(getApiErrorMessage(apiError, "Unable to fetch briefing session."));
        } else {
          setStreamHealth("reconnecting");
          setConnectionNotice("Live updates are reconnecting. Your latest saved progress is still shown below.");
        }
        return null;
      }

      if (data) {
        handleSessionSnapshot(data);
        setConnectionNotice(null);
        setStreamHealth("live");
      }

      return data ?? null;
    };

    const streamSession = async () => {
      let data = prefetchedSnapshot;
      if (!data) {
        data = await refreshSessionSnapshot(sessionId, true);
      } else if (data.state !== "ready" && data.state !== "failed") {
        void refreshSessionSnapshot(sessionId, false);
      }

      if (!data) {
        setInitialSnapshotLoaded(true);
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
            setStreamHealth("live");
            setConnectionNotice(null);
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
            setStreamHealth("reconnecting");
            setConnectionNotice(
              streamError instanceof Error && streamError.message.includes("live session stream")
                ? "Live updates are reconnecting. Your latest saved progress is still shown below."
                : "The live connection dropped for a moment. Reconnecting now."
            );
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

    void streamSession();

    return () => {
      abortController.abort();
    };
  }, [accessToken, loading, router, sessionId, signInPath]);

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

  const isReady = session?.state === "ready";
  const isFailed = session?.state === "failed";
  const isStreaming = Boolean(session && !isReady && !isFailed);
  const rawMarkdown = streamedMarkdown || session?.briefing_markdown || "";
  const markdownToRender = removeGenericBriefingHeading(rawMarkdown);
  const parsedBriefing = useMemo(
    () => parseBriefingMarkdown(markdownToRender, session?.source_title),
    [markdownToRender, session?.source_title]
  );
  const hasMarkdown = Boolean(markdownToRender);
  const clampedProgress = Math.max(0, Math.min(progress, 100));
  const stageLabel = session ? STATE_LABELS[session.state] : "Preparing your briefing";
  const phaseHint = session ? STATE_HINTS[session.state] : "Connecting you to live updates and checking the current session.";
  const headline = isReady
    ? parsedBriefing.title
    : isFailed
      ? "This briefing failed"
      : hasMarkdown
        ? parsedBriefing.title
        : "Building your briefing";
  const subhead = isFailed
      ? "The run stopped before the final briefing was delivered."
      : !isReady
        ? "Talven is working through the source and shaping the briefing."
        : "";
  const showProgressPanel = initialSnapshotLoaded && !hasMarkdown && !isReady && !isFailed;
  const creditCtaMessage = session?.error_message ?? sessionLoadError;
  const showCreditCta = Boolean(creditCtaMessage && isCreditError(creditCtaMessage));
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
  const sourceUrl = session?.canonical_source_url ?? session?.submitted_url ?? "";
  const sourceActionLabel = session?.source_type === "youtube" ? "Original video" : "Original source";
  const sourceLabel = session?.source_type === "youtube" ? "YouTube" : "Source";
  const sourceDurationLabel = session?.source_duration_seconds ? formatExactDuration(session.source_duration_seconds) : null;
  const hasTopActions = canShowReader && !isFailed;
  const heroEyebrow = isFailed ? "Briefing failed" : !isReady ? stageLabel : "";
  const showHeroTopline = Boolean(heroEyebrow || isFailed || showHeroLivePill);
  const navigationSections = [
    parsedBriefing.summary ? { id: "briefing-summary", label: "Summary" } : null,
    parsedBriefing.takeaways ? { id: "briefing-takeaways", label: "Takeaways" } : null,
    ...parsedBriefing.articleSections.map((section) => ({ id: section.id, label: section.title })),
    parsedBriefing.references ? { id: parsedBriefing.references.id, label: "References" } : null
  ].filter((item): item is { id: string; label: string } => Boolean(item));

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader
        active="briefings"
        remainingSeconds={remainingSeconds}
        accountLabel={getAccountLabel(user)}
        onSignOut={signOut}
      />

      <main className={chrome.mainFrame}>
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
                    {showHeroLivePill ? <span className={`${chrome.statusPillMuted} ${styles.liveStatus}`}>Live</span> : null}
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
              <span className={`${chrome.statusPillMuted} ${styles.liveStatus}`}>
                {streamHealth === "reconnecting" ? "Reconnecting" : "Live"}
              </span>
              <p className={styles.loadingSignalText}>{LOADING_SUPPORT_MESSAGES[loadingSupportIndex]}</p>
            </div>

            {connectionNotice ? (
              <div className={styles.connectionCard}>
                <p>{connectionNotice}</p>
              </div>
            ) : null}
          </section>
        ) : canShowReader ? (
          <section className={styles.briefingLayout}>
            <article className={styles.briefingReader}>
              {isStreaming && liveReaderMessage ? (
                <div className={styles.liveReaderBanner}>
                  <div className={styles.liveReaderMeta}>
                    <span className={`${chrome.statusPillMuted} ${styles.liveStatus}`}>
                      {streamHealth === "reconnecting" ? "Reconnecting" : stageLabel}
                    </span>
                    <p className={chrome.surfaceText}>{liveReaderMessage}</p>
                  </div>
                  <span className={styles.liveProgressLabel}>{clampedProgress}% complete</span>
                </div>
              ) : null}

              {connectionNotice ? (
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
                  <StreamingMarkdown markdown={parsedBriefing.takeaways} className={`${styles.markdown} ${styles.takeawayMarkdown}`} />
                </section>
              ) : null}

              {parsedBriefing.articleSections.length ? (
                <div className={styles.articleStack}>
                  {parsedBriefing.articleSections.map((section) => (
                    <BriefingContentSection section={section} key={section.id} />
                  ))}
                </div>
              ) : markdownToRender ? (
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
                  <h2 className={chrome.surfaceTitle}>Contents</h2>
                  <div className={styles.contentsList}>
                    {navigationSections.map((section) => (
                      <a href={`#${section.id}`} key={section.id}>
                        {section.label}
                      </a>
                    ))}
                  </div>
                </nav>
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
                  <p>Error: {session?.error_message ?? "This briefing failed."}</p>
                  {showCreditCta ? (
                    <div className={chrome.actionRow}>
                      <Link className={chrome.primaryButton} href="/app/billing#billing-offers">
                        Get more listening time
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

  const articleSections = bodySections.length
    ? bodySections.map((section) => ({
        ...section,
        title: humanizeSectionTitle(section.title)
      }))
    : cleanedMarkdown
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
  return markdown
    .replace(/^(\s*[-*+]\s*)(?:[\u2705\u26a0\ufe0f]|\u{1f4a1})\s*/gmu, "$1")
    .replace(/^((?:[\u2705\u26a0\ufe0f]|\u{1f4a1})\s*)+/gmu, "");
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

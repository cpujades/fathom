"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";

import { createApiClient } from "@fathom/api-client";

import { AppShellHeader } from "../../../../components/AppShellHeader";
import { useAppShell } from "../../../../components/AppShellProvider";
import chrome from "../../../../components/app-chrome";
import { getApiErrorMessage } from "../../../../lib/apiErrors";
import { getAccountLabel } from "../../../../lib/accountLabel";
import { formatExactDuration } from "../../../../lib/format";
import {
  assertAuthenticatedRequestScopeCurrent,
  captureAuthenticatedRequestScope,
  evictSessionSnapshot,
  invalidateBriefingsCache
} from "../../../../lib/appDataCache";
import { buildSignInPath } from "../../../../lib/url";
import {
  buildMarkdownFilename,
  getDeliveryFailurePresentation,
  getFailurePresentation,
  getFinalizationPresentation,
  isBillingAdmissionErrorCode
} from "../../sessionPresentation";
import { parseTakeawayItems } from "../../takeawayParser";
import {
  parseBriefingMarkdown,
  removeGenericBriefingHeading
} from "../../briefingMarkdown";
import { buildMarkdownExport, copyMarkdownToClipboard } from "../../markdownExport";
import { BriefingReader } from "../../BriefingReader";
import { BriefingSessionHero } from "../../BriefingSessionHero";
import { PublicationActions } from "../../PublicationActions";
import {
  getLifecycleStepIndex,
  getLongRunningNotice,
  STATE_HINTS,
  STATE_LABELS
} from "../../sessionLifecycle";
import { useBriefingSession } from "../../useBriefingSession";

type ExportFeedback = {
  kind: "error" | "success";
  message: string;
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
  const {
    accessToken,
    hasActivePaidSubscription,
    loading,
    refreshUsage,
    remainingSeconds,
    signOut,
    user
  } = useAppShell();
  const userId = user?.id ?? null;
  const { retrySessionLoad, sessionLoadError, sessionLoadErrorCode, sessionState } = useBriefingSession({
    accessToken,
    loading,
    sessionId,
    userId
  });
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [copyLoading, setCopyLoading] = useState(false);
  const [exportFeedback, setExportFeedback] = useState<ExportFeedback | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteConfirming, setDeleteConfirming] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [readingProgress, setReadingProgress] = useState(0);
  const [showReaderContext, setShowReaderContext] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const heroCardRef = useRef<HTMLDivElement | null>(null);
  const refreshedUsageSessionRef = useRef<string | null>(null);
  const {
    connectionNotice,
    markdown: streamedMarkdown,
    phase,
    session,
    streamHealth
  } = sessionState;

  useEffect(() => {
    if (!loading && sessionId && (!accessToken || !userId)) {
      router.replace(signInPath);
    }
  }, [accessToken, loading, router, sessionId, signInPath, userId]);

  useEffect(() => {
    setPdfUrl(null);
    setPdfError(null);
    setCopyLoading(false);
    setExportFeedback(null);
    setDeleteLoading(false);
    setDeleteConfirming(false);
    setActionError(null);
    setShowReaderContext(false);
  }, [sessionId]);

  const handlePdfAction = async () => {
    if (!session?.briefing_id || !accessToken || !userId) {
      return;
    }

    setPdfError(null);
    setExportFeedback(null);
    setPdfLoading(true);

    try {
      const requestScope = captureAuthenticatedRequestScope(userId);
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
      assertAuthenticatedRequestScopeCurrent(requestScope);

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
        setExportFeedback({
          kind: "success",
          message: "PDF ready. Choose Download PDF to open it."
        });
      } else {
        setPdfError("The PDF finished without a download link. Try again.");
      }
    } catch (err) {
      setPdfError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setPdfLoading(false);
    }
  };

  const handleDeleteSession = async () => {
    if (!accessToken || !userId || !sessionId || deleteLoading) {
      return;
    }

    setDeleteLoading(true);
    setActionError(null);

    try {
      const requestScope = captureAuthenticatedRequestScope(userId);
      const api = createApiClient(accessToken);
      const { error } = await api.DELETE("/briefing-sessions/{session_id}", {
        params: {
          path: {
            session_id: sessionId
          }
        }
      });
      assertAuthenticatedRequestScopeCurrent(requestScope);

      if (error) {
        setActionError(getApiErrorMessage(error, "Unable to archive this briefing."));
        return;
      }

      evictSessionSnapshot(userId, sessionId);
      invalidateBriefingsCache(userId);
      setDeleteConfirming(false);
      router.replace("/app/briefings");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Unable to archive this briefing.");
    } finally {
      setDeleteLoading(false);
    }
  };

  const isReady = phase === "ready";
  const isFailed = phase === "failed";
  const isLoadFailed = phase === "load_failed";
  const isDeliveryFailed = phase === "delivery_failed";
  const isStreaming = phase === "streaming";
  const sourceUrl = session?.canonical_source_url ?? session?.submitted_url ?? "";
  const failurePresentation = isDeliveryFailed
    ? getDeliveryFailurePresentation()
    : getFailurePresentation(
        session,
        sessionLoadError,
        sessionLoadErrorCode,
        sourceUrl,
        hasActivePaidSubscription
      );
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
    : isFailed || isLoadFailed || isDeliveryFailed
      ? failurePresentation.title
      : hasMarkdown
        ? parsedBriefing.title
        : session?.source_title || "Opening briefing";
  const subhead = isFailed || isLoadFailed || isDeliveryFailed ? failurePresentation.description : "";
  const showCreditCta = isBillingAdmissionErrorCode(session?.error_code ?? sessionLoadErrorCode);
  const canShowReader = phase === "streaming" || phase === "ready" || phase === "failed";
  const showLifecyclePanel =
    phase !== "ready" && phase !== "failed" && phase !== "load_failed" && phase !== "delivery_failed";
  const lifecycleStepIndex = getLifecycleStepIndex(session?.state ?? null, phase);
  const lifecycleKicker = phase === "loading_session" ? "Reader" : "Briefing in progress";
  const defaultLifecycleTitle = phase === "loading_session" ? "Opening reader" : stageLabel;
  const defaultLifecycleHint =
    phase === "loading_session"
      ? "A live reader is being prepared."
      : phaseHint;
  const finalizationPresentation = getFinalizationPresentation(
    session?.error_code,
    defaultLifecycleTitle,
    defaultLifecycleHint
  );
  const lifecycleTitle = finalizationPresentation.label;
  const lifecycleHint = finalizationPresentation.hint;
  const lifecycleStatusLabel =
    streamHealth === "reconnecting"
      ? "Reconnecting"
      : phase === "loading_session"
        ? "Opening"
        : finalizationPresentation.status;
  const primaryPdfActionLabel = pdfLoading
    ? session?.briefing_has_pdf
      ? "Opening PDF..."
      : "Preparing PDF..."
    : session?.briefing_has_pdf || pdfUrl
      ? "Download PDF"
      : "Generate PDF";
  const sourceActionLabel = session?.source_type === "youtube" ? "Original video" : "Original source";
  const sourceLabel = session?.source_type === "youtube" ? "YouTube" : "Source";
  const sourceDurationLabel = session?.source_duration_seconds ? formatExactDuration(session.source_duration_seconds) : null;
  const hasTopActions = canShowReader && !isFailed;
  const heroEyebrow = isFailed
    ? "Briefing failed"
    : isLoadFailed || isDeliveryFailed
      ? "Reader unavailable"
      : !isReady
        ? stageLabel
        : "";
  const showHeroTopline = Boolean(heroEyebrow || isFailed || isLoadFailed || isDeliveryFailed);
  const navigationSections = [
    parsedBriefing.summary ? { id: "briefing-summary", label: "Summary" } : null,
    parsedBriefing.takeaways ? { id: "briefing-takeaways", label: "Takeaways" } : null,
    ...parsedBriefing.articleSections.map((section) => ({ id: section.id, label: section.title })),
    parsedBriefing.references ? { id: parsedBriefing.references.id, label: "References" } : null
  ].filter((item): item is { id: string; label: string } => Boolean(item));
  const mobileNavigationSections = navigationSections.slice(0, 3);

  const handleMarkdownDownload = () => {
    if (!isReady || !rawMarkdown.trim()) {
      return;
    }

    const objectUrl = URL.createObjectURL(
      new Blob([buildMarkdownExport(rawMarkdown)], {
        type: "text/markdown;charset=utf-8"
      })
    );
    const downloadLink = document.createElement("a");
    downloadLink.href = objectUrl;
    downloadLink.download = buildMarkdownFilename(session?.source_title ?? parsedBriefing.title);
    document.body.append(downloadLink);
    downloadLink.click();
    downloadLink.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    setExportFeedback({ kind: "success", message: "Markdown downloaded." });
  };

  const handleMarkdownCopy = async () => {
    if (!isReady || !rawMarkdown.trim() || copyLoading) {
      return;
    }

    setCopyLoading(true);
    setExportFeedback(null);

    try {
      await copyMarkdownToClipboard(rawMarkdown, window.navigator.clipboard);
      setExportFeedback({
        kind: "success",
        message: "Markdown copied. It is ready to paste into your notes."
      });
    } catch {
      setExportFeedback({
        kind: "error",
        message: "Could not copy the Markdown. Download the .md file instead."
      });
    } finally {
      setCopyLoading(false);
    }
  };

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

  useEffect(() => {
    if (!canShowReader) {
      setShowReaderContext(false);
      return undefined;
    }

    const heroCard = heroCardRef.current;
    if (!heroCard || typeof IntersectionObserver === "undefined") {
      return undefined;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        setShowReaderContext(!entry.isIntersecting);
      },
      {
        rootMargin: "-80px 0px 0px",
        threshold: 0
      }
    );

    observer.observe(heroCard);
    return () => observer.disconnect();
  }, [canShowReader, sessionId]);

  useEffect(() => {
    if (!deleteConfirming) {
      return;
    }

    window.requestAnimationFrame(() => {
      focusFirstVisibleControl("[data-remove-cancel]");
    });
  }, [deleteConfirming]);

  const closeDeleteConfirmation = () => {
    if (deleteLoading) {
      return;
    }
    setDeleteConfirming(false);
    window.requestAnimationFrame(() => {
      focusFirstVisibleControl("[data-remove-trigger]");
    });
  };

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader
        active="briefings"
        remainingSeconds={remainingSeconds}
        accountLabel={getAccountLabel(user)}
        onSignOut={signOut}
      />

      <main id="main-content" className={chrome.mainFrame}>
        <div id="briefing-hero" ref={heroCardRef}>
          <BriefingSessionHero
            connectionNotice={connectionNotice}
            copyLoading={copyLoading}
            exportFeedback={exportFeedback}
            failureActionHref={failurePresentation.actionHref}
            failureActionLabel={failurePresentation.actionLabel}
            failureDetail={failurePresentation.detail}
            hasTopActions={hasTopActions}
            headline={headline}
            heroEyebrow={heroEyebrow}
            isDeliveryFailed={isDeliveryFailed}
            isFailed={isFailed}
            isLoadFailed={isLoadFailed}
            isReady={isReady}
            lifecycleHint={lifecycleHint}
            lifecycleKicker={lifecycleKicker}
            lifecycleStatusLabel={lifecycleStatusLabel}
            lifecycleStepIndex={lifecycleStepIndex}
            lifecycleTitle={lifecycleTitle}
            longRunningNotice={longRunningNotice}
            onCopyMarkdown={handleMarkdownCopy}
            onDownloadMarkdown={handleMarkdownDownload}
            onOpenPdf={handlePdfAction}
            onRetry={retrySessionLoad}
            pdfError={pdfError}
            pdfLoading={pdfLoading}
            pdfUrl={pdfUrl}
            phase={phase}
            primaryPdfActionLabel={primaryPdfActionLabel}
            rawMarkdown={rawMarkdown}
            session={session}
            sessionLoadError={sessionLoadError}
            showCreditCta={showCreditCta}
            showHeroTopline={showHeroTopline}
            showLifecyclePanel={showLifecyclePanel}
            sourceActionLabel={sourceActionLabel}
            sourceDurationLabel={sourceDurationLabel}
            sourceLabel={sourceLabel}
            sourceUrl={sourceUrl}
            streamHealth={streamHealth}
            subhead={subhead}
          />
        </div>

        {isReady && accessToken ? (
          <PublicationActions
            accessToken={accessToken}
            sessionId={sessionId}
            title={parsedBriefing.title}
          />
        ) : null}

        {canShowReader ? (
          <BriefingReader
            actionError={actionError}
            connectionNotice={connectionNotice}
            deleteConfirming={deleteConfirming}
            deleteLoading={deleteLoading}
            failureActionHref={failurePresentation.actionHref}
            failureActionLabel={failurePresentation.actionLabel}
            failureDetail={failurePresentation.detail}
            isFailed={isFailed}
            isReady={isReady}
            isStreaming={isStreaming}
            markdownToRender={markdownToRender}
            mobileNavigationSections={mobileNavigationSections}
            navigationSections={navigationSections}
            onCancelDelete={closeDeleteConfirmation}
            onConfirmDelete={handleDeleteSession}
            onOpenPdf={handlePdfAction}
            onRequestDelete={() => {
              setDeleteConfirming(true);
              setActionError(null);
            }}
            parsedBriefing={parsedBriefing}
            pdfLoading={pdfLoading}
            pdfUrl={pdfUrl}
            primaryPdfActionLabel={primaryPdfActionLabel}
            readingProgress={readingProgress}
            session={session}
            showNowReading={showReaderContext}
            showLifecyclePanel={showLifecyclePanel}
            takeawayItems={takeawayItems}
          />
        ) : null}
      </main>
    </div>
  );
}

function focusFirstVisibleControl(selector: string): void {
  const controls = Array.from(document.querySelectorAll<HTMLElement>(selector));
  controls.find((control) => control.getClientRects().length > 0)?.focus();
}

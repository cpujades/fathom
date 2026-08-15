"use client";

import { type FormEvent, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { createApiClient } from "@fathom/api-client";
import type { ExploreBriefingItem, PublicationLibraryEntryResponse } from "@fathom/api-client";

import { AppShellHeader } from "../../../components/AppShellHeader";
import { useAppShell } from "../../../components/AppShellProvider";
import chrome from "../../../components/app-chrome";
import {
  getApiErrorCode,
  getApiErrorDetails,
  getApiErrorMessage,
  type ApiErrorDetails
} from "../../../lib/apiErrors";
import { getAccountLabel } from "../../../lib/accountLabel";
import { formatExploreTopic } from "../../../lib/format";
import {
  assertAuthenticatedRequestScopeCurrent,
  cacheSessionSnapshot,
  captureAuthenticatedRequestScope,
  invalidateBriefingsCache
} from "../../../lib/appDataCache";
import { buildSignInPath } from "../../../lib/url";
import { getAdmissionFailurePresentation } from "../admissionPresentation";
import styles from "../session-create.module.css";

type CreatePhase = "idle" | "checking" | "available" | "creating" | "opening" | "error";

type CreateError = {
  code: string | null;
  details: ApiErrorDetails | null;
  message: string;
};

const PHASE_COPY: Record<CreatePhase, { description: string; status: string; title: string }> = {
  idle: {
    title: "Paste a source",
    description: "Start with a public YouTube URL.",
    status: "Ready"
  },
  checking: {
    title: "Finding the source",
    description: "A clean briefing starts with a clean source.",
    status: "Checking"
  },
  available: {
    title: "A briefing is already ready",
    description: "Read it now or save it to your library without using video time.",
    status: "Available"
  },
  creating: {
    title: "Preparing your briefing",
    description: "Talven is getting the source ready.",
    status: "Starting"
  },
  opening: {
    title: "Opening reader",
    description: "The briefing is ready to begin.",
    status: "Opening"
  },
  error: {
    title: "Needs a better source",
    description: "Try a public YouTube URL.",
    status: "Review"
  }
};

const CREATE_STEP_KEYS = ["source", "transcribe", "write", "ready"] as const;

function BriefingCreatePageContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const {
    accessToken,
    hasActivePaidSubscription,
    loading,
    remainingSeconds,
    signOut,
    user
  } = useAppShell();
  const userId = user?.id ?? null;
  const initialUrl = useMemo(() => searchParams.get("url")?.trim() ?? "", [searchParams]);
  const confirmSameSourceRetry = searchParams.get("confirm") === "retry";
  const [draftUrl, setDraftUrl] = useState(initialUrl);
  const [createError, setCreateError] = useState<CreateError | null>(null);
  const [matchedPublication, setMatchedPublication] = useState<ExploreBriefingItem | null>(null);
  const [matchedLibraryEntry, setMatchedLibraryEntry] = useState<PublicationLibraryEntryResponse | null>(null);
  const [phase, setPhase] = useState<CreatePhase>(
    initialUrl && !confirmSameSourceRetry ? "checking" : "idle"
  );
  const [submitting, setSubmitting] = useState(false);
  const startedRef = useRef(false);
  const signInPath = buildSignInPath(
    `${pathname}${searchParams.toString() ? `?${searchParams.toString()}` : ""}`
  );

  useEffect(() => {
    setDraftUrl(initialUrl);
    if (!startedRef.current) {
      setPhase(initialUrl && !confirmSameSourceRetry ? "checking" : "idle");
    }
  }, [confirmSameSourceRetry, initialUrl]);

  const startSession = useCallback(
    async (rawUrl: string) => {
      if (!accessToken || !userId || submitting) {
        return;
      }

      const normalizedUrl = normalizeSourceUrl(rawUrl);
      if (!normalizedUrl) {
        setPhase("error");
        setCreateError({
          code: "invalid_request",
          details: null,
          message: "Paste a full public YouTube URL beginning with http:// or https://."
        });
        return;
      }

      setSubmitting(true);
      setCreateError(null);
      setMatchedPublication(null);
      setMatchedLibraryEntry(null);
      setPhase("checking");

      try {
        const requestScope = captureAuthenticatedRequestScope(userId);
        const api = createApiClient(accessToken);
        const matchResponse = await api.GET("/publications/source-match", {
          params: { query: { url: normalizedUrl } }
        });
        assertAuthenticatedRequestScopeCurrent(requestScope);
        if (matchResponse.error) {
          setPhase("error");
          setCreateError({
            code: getApiErrorCode(matchResponse.error),
            details: getApiErrorDetails(matchResponse.error),
            message: getApiErrorMessage(matchResponse.error, "Unable to check existing briefings.")
          });
          return;
        }
        if (matchResponse.data?.match) {
          setMatchedPublication(matchResponse.data.match);
          setMatchedLibraryEntry(matchResponse.data.library_entry ?? null);
          setPhase("available");
          return;
        }

        setPhase("creating");
        const { data, error: apiError } = await api.POST("/briefing-sessions", {
          body: {
            url: normalizedUrl
          }
        });
        assertAuthenticatedRequestScopeCurrent(requestScope);

        if (apiError) {
          if (getApiErrorCode(apiError) === "public_briefing_available") {
            const retryMatch = await api.GET("/publications/source-match", {
              params: { query: { url: normalizedUrl } }
            });
            assertAuthenticatedRequestScopeCurrent(requestScope);
            if (retryMatch.data?.match) {
              setMatchedPublication(retryMatch.data.match);
              setMatchedLibraryEntry(retryMatch.data.library_entry ?? null);
              setPhase("available");
              return;
            }
          }
          setPhase("error");
          setCreateError({
            code: getApiErrorCode(apiError),
            details: getApiErrorDetails(apiError),
            message: getApiErrorMessage(apiError, "Unable to start the briefing.")
          });
          return;
        }

        if (data?.session_id) {
          setPhase("opening");
          cacheSessionSnapshot(userId, data);
          invalidateBriefingsCache(userId);
          router.replace(`/app/briefings/sessions/${data.session_id}`);
          return;
        }

        setPhase("error");
        setCreateError({ code: null, details: null, message: "Unexpected response from the server." });
      } catch (err) {
        setPhase("error");
        setCreateError({
          code: null,
          details: null,
          message: err instanceof Error ? err.message : "Something went wrong."
        });
      } finally {
        setSubmitting(false);
      }
    },
    [accessToken, router, submitting, userId]
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

    if (confirmSameSourceRetry && initialUrl) {
      setPhase("idle");
      setCreateError(null);
      return;
    }

    if (!initialUrl) {
      setPhase("idle");
      setCreateError({
        code: "invalid_request",
        details: null,
        message: "No source link reached this step. Paste one below to continue."
      });
      setPhase("error");
      return;
    }

    void startSession(initialUrl);
  }, [accessToken, confirmSameSourceRetry, initialUrl, loading, router, signInPath, startSession]);

  const handleRetry = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextUrl = draftUrl.trim();
    if (!nextUrl) {
      setPhase("error");
      setCreateError({
        code: "invalid_request",
        details: null,
        message: "Paste a valid public YouTube URL to start a briefing."
      });
      return;
    }

    await startSession(nextUrl);
  };

  const saveMatchedPublication = async () => {
    if (!matchedPublication || !accessToken || !userId || submitting) return;
    setSubmitting(true);
    setCreateError(null);
    try {
      const requestScope = captureAuthenticatedRequestScope(userId);
      const api = createApiClient(accessToken);
      const { data, error: apiError } = await api.POST("/publications/{public_slug}/save", {
        params: { path: { public_slug: matchedPublication.public_slug } }
      });
      assertAuthenticatedRequestScopeCurrent(requestScope);
      if (apiError || !data?.session_path) {
        setCreateError({
          code: apiError ? getApiErrorCode(apiError) : null,
          details: apiError ? getApiErrorDetails(apiError) : null,
          message: apiError
            ? getApiErrorMessage(apiError, "Unable to save this briefing.")
            : "The briefing was saved without a library link."
        });
        return;
      }
      invalidateBriefingsCache(userId);
      setPhase("opening");
      router.replace(data.session_path);
    } catch (saveError) {
      setCreateError({
        code: null,
        details: null,
        message: saveError instanceof Error ? saveError.message : "Unable to save this briefing."
      });
    } finally {
      setSubmitting(false);
    }
  };

  const admissionFailure = createError
    ? getAdmissionFailurePresentation(
        createError.code,
        createError.message,
        createError.details,
        hasActivePaidSubscription
      )
    : null;
  const phaseCopy = admissionFailure
    ? {
        title: admissionFailure.title,
        description: admissionFailure.description,
        status: "Review"
      }
    : confirmSameSourceRetry && phase === "idle"
      ? {
          title: "Try this source again",
          description: "Your source is ready. Confirm below when you want Talven to start a new briefing.",
          status: "Ready"
        }
      : PHASE_COPY[phase];
  const sourceHost = getSourceHost(draftUrl);
  const activeStepIndex = getActiveCreateStepIndex(phase);
  const showSourceForm = (Boolean(createError) && phase !== "available") || (confirmSameSourceRetry && phase === "idle");

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader
        active={null}
        remainingSeconds={remainingSeconds}
        accountLabel={getAccountLabel(user)}
        onSignOut={signOut}
      />

      <main id="main-content" className={chrome.mainFrame}>
        <section className={styles.createShell}>
          <article className={`${styles.sessionHero} ${styles.createCard}`} aria-live="polite">
            <div className={styles.createHeader}>
              <div>
                <p className={styles.createKicker}>Briefing</p>
                <h1 className={styles.createTitle}>{phaseCopy.title}</h1>
                <p className={styles.createText}>{phaseCopy.description}</p>
              </div>
              <span className={phase === "error" ? chrome.statusPillWarning : chrome.statusPillMuted}>{phaseCopy.status}</span>
            </div>

            {sourceHost ? (
              <p className={styles.createSourceLine}>
                Source <span>{sourceHost}</span>
              </p>
            ) : null}

            <div className={styles.lifecycleSteps}>
              {CREATE_STEP_KEYS.map((stepKey, index) => (
                <div className={getCreateStepClassName(index, activeStepIndex, phase)} key={stepKey}>
                  <span aria-hidden="true" />
                  <div>
                    <p>{getCreateStepLabel(stepKey)}</p>
                    <small>
                      {getCreateStepHint(stepKey, sourceHost, phase)}
                      {index === activeStepIndex && !["idle", "available", "error"].includes(phase) ? (
                        <span className={styles.lifecycleEllipsis} aria-hidden="true" />
                      ) : null}
                    </small>
                  </div>
                </div>
              ))}
            </div>

            {phase === "available" && matchedPublication ? (
              <div className={styles.availableCard}>
                <div>
                  <p className={styles.availableTopic}>{formatExploreTopic(matchedPublication.topic)}</p>
                  <h2>{matchedPublication.title}</h2>
                  {matchedPublication.author ? <p>By {matchedPublication.author}</p> : null}
                </div>
                <div className={chrome.actionRow}>
                  <Link className={chrome.primaryButton} href={matchedPublication.public_path}>Open free briefing</Link>
                  {matchedLibraryEntry?.session_path ? (
                    <Link className={chrome.secondaryButton} href={matchedLibraryEntry.session_path}>
                      {matchedLibraryEntry.state === "processing" ? "Open current briefing" : "Open in library"}
                    </Link>
                  ) : (
                    <button
                      className={chrome.secondaryButton}
                      type="button"
                      onClick={() => void saveMatchedPublication()}
                      disabled={submitting}
                    >
                      {submitting ? "Saving…" : "Save to library"}
                    </button>
                  )}
                </div>
                {createError ? <p className={styles.availableError} role="alert">{createError.message}</p> : null}
                <p className={styles.availableNote}>
                  {matchedLibraryEntry?.session_path
                    ? "Already in your library. Opening it uses no video time."
                    : "Saving reuses the ready briefing and uses no video time."}
                </p>
              </div>
            ) : null}

            {showSourceForm ? (
              <form
                className={createError ? styles.errorCard : styles.sourceFormCard}
                onSubmit={(event) => void handleRetry(event)}
                aria-describedby={createError ? "create-error" : "create-retry-help"}
              >
                {admissionFailure ? (
                  <p id="create-error" role="alert">
                    {admissionFailure.detail}
                  </p>
                ) : (
                  <p id="create-retry-help">
                    Review the source, then choose Try again to start a new briefing explicitly.
                  </p>
                )}
                <label className={chrome.fieldStack}>
                  <span className={chrome.fieldLabel}>Public YouTube URL</span>
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
                  <button className={chrome.primaryButton} type="submit" disabled={submitting}>
                    {submitting ? "Starting..." : admissionFailure?.retryLabel ?? "Try again"}
                  </button>
                  <Link className={chrome.secondaryButton} href="/app">
                    Back to workspace
                  </Link>
                </div>
                {admissionFailure?.billingAction ? (
                  <div className={chrome.actionRow}>
                    <Link className={chrome.primaryButton} href={admissionFailure.billingAction.href}>
                      {admissionFailure.billingAction.label}
                    </Link>
                  </div>
                ) : null}
              </form>
            ) : (
              <div className={styles.createFooter}>
                <Link className={styles.textActionLink} href="/app">
                  Back to workspace
                </Link>
              </div>
            )}
          </article>
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
          <main id="main-content" className={chrome.mainFrame}>
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

function getActiveCreateStepIndex(phase: CreatePhase): number {
  return phase === "available" || phase === "opening" ? CREATE_STEP_KEYS.length - 1 : 0;
}

function getCreateStepLabel(stepKey: (typeof CREATE_STEP_KEYS)[number]): string {
  if (stepKey === "source") {
    return "Check source";
  }
  if (stepKey === "transcribe") {
    return "Transcribe";
  }
  if (stepKey === "write") {
    return "Write";
  }
  return "Ready";
}

function getCreateStepHint(stepKey: (typeof CREATE_STEP_KEYS)[number], sourceHost: string | null, phase: CreatePhase): string {
  if (stepKey === "source") {
    if (phase === "available" || phase === "opening") {
      return "Source ready.";
    }
    return sourceHost ? sourceHost : "Source";
  }
  if (stepKey === "transcribe") {
    return phase === "available" ? "Transcript ready." : "Waiting for source.";
  }
  if (stepKey === "write") {
    return phase === "available" ? "Briefing ready." : "Waiting for transcript.";
  }
  if (phase === "available") {
    return "Available now.";
  }
  return phase === "opening" ? "Opening reader." : "Waiting for briefing.";
}

function getSourceHost(rawUrl: string): string | null {
  try {
    return new URL(rawUrl.trim()).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

function getCreateStepClassName(index: number, activeStepIndex: number, phase: CreatePhase): string {
  if (phase === "error" && index === activeStepIndex) {
    return `${styles.lifecycleStep} ${styles.lifecycleStepActive}`;
  }
  if (index < activeStepIndex) {
    return `${styles.lifecycleStep} ${styles.lifecycleStepComplete}`;
  }
  if (index === activeStepIndex) {
    return `${styles.lifecycleStep} ${styles.lifecycleStepActive}`;
  }
  return styles.lifecycleStep;
}

function normalizeSourceUrl(rawUrl: string): string | null {
  try {
    const parsed = new URL(rawUrl.trim());
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return null;
    }
    return parsed.toString();
  } catch {
    return null;
  }
}

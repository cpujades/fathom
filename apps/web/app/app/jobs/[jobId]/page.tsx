"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import type { JobStatusResponse, SummaryResponse } from "@fathom/api-client";
import type { RealtimeChannel, SupabaseClient } from "@supabase/supabase-js";
import { createApiClient } from "@fathom/api-client";
import styles from "./job.module.css";
import { getApiErrorMessage } from "../../../lib/apiErrors";
import { getSupabaseClient } from "../../../lib/supabaseClient";
import { StreamingMarkdown } from "../../../components/StreamingMarkdown";

const POLL_INTERVAL_MS = 2000;
const STAGE_FALLBACK: Record<string, number> = {
  queued: 8,
  running: 20,
  warming: 15,
  transcribing: 35,
  checking_cache: 50,
  summarizing: 65,
  rendering: 85,
  completed: 100,
  cached: 100,
  failed: 100
};

export default function JobDetailPage() {
  const router = useRouter();
  const params = useParams();
  const jobId = useMemo(() => params?.jobId?.toString() ?? "", [params]);
  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(5);
  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const realtimeChannelRef = useRef<RealtimeChannel | null>(null);
  const realtimeClientRef = useRef<SupabaseClient | null>(null);

  const updateProgress = useCallback((payload: JobStatusResponse) => {
    if (typeof payload.progress === "number") {
      setProgress(payload.progress);
    } else if (payload.stage && STAGE_FALLBACK[payload.stage]) {
      setProgress(STAGE_FALLBACK[payload.stage]);
    } else {
      switch (payload.status) {
        case "queued":
          setProgress(10);
          break;
        case "running":
          setProgress((prev) => Math.max(prev, 50));
          break;
        case "succeeded":
        case "failed":
          setProgress(100);
          break;
        default:
          break;
      }
    }
  }, []);

  const fetchSummary = useCallback(async (summaryId: string, accessToken: string) => {
    const api = createApiClient(accessToken);
    const { data: summaryData, error: summaryError } = await api.GET("/summaries/{summary_id}", {
      params: {
        path: {
          summary_id: summaryId
        }
      }
    });

    if (summaryError) {
      setError(getApiErrorMessage(summaryError, "Unable to fetch summary."));
      return;
    }

    if (summaryData) {
      setSummary(summaryData);
      setPdfUrl(summaryData.pdf_url ?? null);
    }
  }, []);

  const handleJobPayload = useCallback(async (payload: JobStatusResponse, accessToken: string) => {
    setJob(payload);
    updateProgress(payload);

    const isStageComplete = payload.stage === "completed" || payload.stage === "cached";

    if ((payload.status === "succeeded" || isStageComplete) && payload.summary_id) {
      await fetchSummary(payload.summary_id, accessToken);
      return true;
    }

    if (payload.status === "failed") {
      return true;
    }

    return false;
  }, [fetchSummary, updateProgress]);

  const startPolling = useCallback((accessToken: string) => {
    if (pollingRef.current) {
      return;
    }

    let delay = POLL_INTERVAL_MS;
    const poll = async () => {
      try {
        const api = createApiClient(accessToken);
        const { data, error: apiError } = await api.GET("/jobs/{job_id}", {
          params: {
            path: {
              job_id: jobId
            }
          }
        });

        if (apiError) {
          const status = (apiError as { status?: number }).status;
          if (status === 429) {
            delay = Math.min(delay * 1.8, 15000);
            pollingRef.current = setTimeout(poll, delay);
            return;
          }
          setError(getApiErrorMessage(apiError, "Unable to fetch job status."));
          return;
        }

        if (data) {
          const isDone = await handleJobPayload(data, accessToken);
          if (!isDone) {
            delay = POLL_INTERVAL_MS;
            pollingRef.current = setTimeout(poll, delay);
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      }
    };

    void poll();
  }, [handleJobPayload, jobId]);

  useEffect(() => {
    if (!jobId) {
      return;
    }

    const init = async () => {
      try {
        const supabase = getSupabaseClient();
        realtimeClientRef.current = supabase;
        const { data: sessionData } = await supabase.auth.getSession();

        if (!sessionData.session) {
          router.replace("/signin");
          return;
        }

        const accessToken = sessionData.session.access_token;
        const userId = sessionData.session.user.id;

        const api = createApiClient(accessToken);
        const { data: initialJob, error: jobError } = await api.GET("/jobs/{job_id}", {
          params: {
            path: {
              job_id: jobId
            }
          }
        });

        if (jobError) {
          setError(getApiErrorMessage(jobError, "Unable to fetch job status."));
        } else if (initialJob) {
          const done = await handleJobPayload(initialJob, accessToken);
          if (done) {
            return;
          }
        }

        const channel = supabase
          .channel(`jobs:${userId}`)
          .on(
            "postgres_changes",
            {
              event: "*",
              schema: "public",
              table: "jobs",
              filter: `user_id=eq.${userId}`
            },
            async (payload) => {
              const row = payload.new as Record<string, unknown> | null;
              if (!row || row.id !== jobId) {
                return;
              }

              const jobPayload: JobStatusResponse = {
                job_id: String(row.id),
                status: row.status as JobStatusResponse["status"],
                summary_id: (row.summary_id as string | null) ?? null,
                error_code: (row.error_code as string | null) ?? null,
                error_message: (row.error_message as string | null) ?? null,
                stage: (row.stage as string | null) ?? null,
                progress: (row.progress as number | null) ?? null,
                status_message: (row.status_message as string | null) ?? null
              };

              const done = await handleJobPayload(jobPayload, accessToken);
              if (done) {
                supabase.removeChannel(channel);
                realtimeChannelRef.current = null;
              }
            }
          )
          .subscribe((status) => {
            if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") {
              startPolling(accessToken);
            }
          });

        realtimeChannelRef.current = channel;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      }
    };

    void init();

    return () => {
      if (pollingRef.current) {
        clearTimeout(pollingRef.current);
        pollingRef.current = null;
      }
      if (realtimeClientRef.current && realtimeChannelRef.current) {
        realtimeClientRef.current.removeChannel(realtimeChannelRef.current);
        realtimeChannelRef.current = null;
      }
    };
  }, [handleJobPayload, jobId, router, startPolling]);

  const isComplete = job?.status === "succeeded" || job?.stage === "completed" || job?.stage === "cached";
  const isFailed = job?.status === "failed";
  const markdownToRender = summary?.markdown ?? "";
  const hasMarkdown = Boolean(markdownToRender);
  const clampedProgress = Math.max(0, Math.min(progress, 100));
  const headline = isComplete
    ? "Briefing ready"
    : isFailed
      ? "Briefing failed"
      : hasMarkdown
        ? "Briefing in progress"
        : "Preparing your briefing";
  const subhead = isComplete
    ? "Your summary is ready to read, export, and share."
    : isFailed
      ? "We ran into an issue. You can try again or start a fresh summary."
      : "We are translating the audio into a clean, structured briefing.";
  const isCached = job?.stage === "cached";
  const isStreaming = !isComplete && !isFailed && !isCached;
  const showProgressPanel = !hasMarkdown && !isComplete && !isFailed && !isCached;

  const statusFallbackStage = job?.status === "running" ? "summarizing" : job?.status ?? "queued";
  const rawStageKey = job?.stage ?? statusFallbackStage;
  const normalizedStage = rawStageKey === "completed" || rawStageKey === "cached" ? "rendering" : rawStageKey;
  const displayStageLabel = (() => {
    if (isComplete) return "Summary ready";
    if (isFailed) return "Needs attention";
    switch (normalizedStage) {
      case "transcribing":
        return "Listening carefully";
      case "summarizing":
        return "Drafting the briefing";
      case "rendering":
        return "Polishing the output";
      default:
        return "Preparing your summary";
    }
  })();

  const handleGeneratePdf = async () => {
    if (!summary?.summary_id) {
      return;
    }

    setPdfError(null);
    setPdfLoading(true);

    try {
      const supabase = getSupabaseClient();
      const { data: sessionData } = await supabase.auth.getSession();

      if (!sessionData.session) {
        router.replace("/signin");
        return;
      }

      const api = createApiClient(sessionData.session.access_token);
      const { data, error: apiError } = await api.POST("/summaries/{summary_id}/pdf", {
        params: {
          path: {
            summary_id: summary.summary_id
          }
        }
      });

      if (apiError) {
        setPdfError(getApiErrorMessage(apiError, "Unable to generate the PDF."));
        return;
      }

      setPdfUrl(data?.pdf_url ?? null);
    } catch (err) {
      setPdfError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setPdfLoading(false);
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true" />
          Fathom
        </div>
        <div className={styles.headerActions}>
          <Link className={styles.headerButton} href="/app">
            Workspace
          </Link>
          <Link className={styles.headerButton} href="/">
            Landing
          </Link>
        </div>
      </header>

      <main className={styles.main}>
        <div className={styles.container}>
          <section className={styles.hero}>
            <h1 className={styles.heroTitle}>{headline}</h1>
            <p className={styles.heroText}>{subhead}</p>
            <div className={styles.heroMeta}>
              <span className={showProgressPanel ? styles.pill : isComplete ? styles.pill : styles.pillMuted}>
                {showProgressPanel ? displayStageLabel : isStreaming ? "Live" : "Final"}
              </span>
            </div>
          </section>

          {showProgressPanel ? (
            <section className={styles.loadingSection}>
              <div className={styles.loadingCard}>
                <div className={styles.loadingTop}>
                  <span className={styles.spinner} aria-hidden="true" />
                  <div>
                    <h2 className={styles.loadingTitle}>Building your briefing</h2>
                    <p className={styles.loadingSubtitle}>{displayStageLabel}</p>
                  </div>
                </div>

                <div className={styles.progressTrack}>
                  <div className={styles.progressFill} style={{ width: `${clampedProgress}%` }} />
                </div>
                <div className={styles.loadingMeta}>
                  <span>Your summary will appear here once it’s ready.</span>
                  <span>Usually a few minutes.</span>
                </div>

                <div className={styles.loadingSteps}>
                  {[
                    { key: "listen", label: "Listening", hint: "Transcribing the audio" },
                    { key: "summarize", label: "Summarizing", hint: "Structuring key insights" },
                    { key: "polish", label: "Polishing", hint: "Final formatting" }
                  ].map((step, index) => {
                    const activeIndex = normalizedStage === "rendering" ? 2 : normalizedStage === "summarizing" ? 1 : 0;
                    const isStepActive = index === activeIndex;
                    const isStepComplete = index < activeIndex;

                    return (
                      <div key={step.key} className={styles.loadingStep}>
                        <span
                          className={`${styles.stageDot} ${
                            isStepComplete
                              ? styles.stageDotComplete
                              : isStepActive
                                ? styles.stageDotActive
                                : ""
                          }`}
                        />
                        <div>
                          <div className={styles.stageLabel}>{step.label}</div>
                          <div className={styles.stageHint}>{step.hint}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {error ? <div className={styles.errorCard}>{error}</div> : null}
              </div>
            </section>
          ) : (
            <section className={styles.layout}>
              <div className={styles.card}>
                <div className={styles.cardHeader}>
                  <div>
                    <h2 className={styles.cardTitle}>Briefing</h2>
                    <p className={styles.cardSubtitle}>
                      {isComplete
                        ? "Your briefing is finalized below."
                        : "We refresh the briefing status as it’s prepared."}
                    </p>
                  </div>
                  <span className={isComplete ? styles.pill : styles.pillMuted}>{isComplete ? "Final" : "Updating"}</span>
                </div>
                <div className={styles.summaryBody}>
                  {markdownToRender ? (
                    <StreamingMarkdown
                      markdown={markdownToRender}
                      isStreaming={false}
                      className={styles.markdown}
                      cursorClassName={styles.streamingCursor}
                    />
                  ) : (
                    <div className={styles.emptyState}>
                      {isFailed
                        ? "We could not render the summary. Try again when you’re ready."
                        : "Your summary will appear here as soon as we have content."}
                    </div>
                  )}
                </div>
              </div>

              <aside className={styles.sideColumn}>
                <div className={styles.card}>
                  <div className={styles.cardHeader}>
                    <div>
                      <h2 className={styles.cardTitle}>Export</h2>
                      <p className={styles.cardSubtitle}>
                        Save the briefing as a PDF or start a new summary.
                      </p>
                    </div>
                  </div>
                  <div className={styles.actions}>
                    {pdfUrl ? (
                      <a className={styles.buttonPrimary} href={pdfUrl} target="_blank" rel="noreferrer">
                        Download PDF
                      </a>
                    ) : (
                      <button
                        className={styles.buttonPrimary}
                        type="button"
                        onClick={handleGeneratePdf}
                        disabled={pdfLoading || !job?.summary_id}
                      >
                        {pdfLoading ? "Preparing PDF…" : "Generate PDF"}
                      </button>
                    )}
                    <Link className={styles.buttonSecondary} href="/app">
                      New summary
                    </Link>
                  </div>
                  {pdfError ? <div className={styles.errorCard}>{pdfError}</div> : null}
                </div>

                {job?.status === "failed" && (
                  <div className={styles.errorCard}>Error: {job.error_message ?? "Job failed."}</div>
                )}
                {error && <div className={styles.errorCard}>{error}</div>}
              </aside>
            </section>
          )}
        </div>
     </main>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import type { JobStatusResponse, SummaryResponse } from "@fathom/api-client";
import type { RealtimeChannel, SupabaseClient, User } from "@supabase/supabase-js";
import { createApiClient } from "@fathom/api-client";

import { AppShellHeader } from "../../../components/AppShellHeader";
import { StreamingMarkdown } from "../../../components/StreamingMarkdown";
import chrome from "../../../components/app-chrome.module.css";
import styles from "./job.module.css";
import { getApiErrorMessage } from "../../../lib/apiErrors";
import { getAccountLabel } from "../../../lib/accountLabel";
import { getSupabaseClient } from "../../../lib/supabaseClient";

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
  const [user, setUser] = useState<User | null>(null);
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
      setError(getApiErrorMessage(summaryError, "Unable to fetch briefing."));
      return;
    }

    if (summaryData) {
      setSummary(summaryData);
      setPdfUrl(summaryData.pdf_url ?? null);
    }
  }, []);

  const handleJobPayload = useCallback(
    async (payload: JobStatusResponse, accessToken: string) => {
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
    },
    [fetchSummary, updateProgress]
  );

  const startPolling = useCallback(
    (accessToken: string) => {
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
    },
    [handleJobPayload, jobId]
  );

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

        setUser(sessionData.session.user);

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

  const handleSignOut = async () => {
    const supabase = getSupabaseClient();
    await supabase.auth.signOut();
    router.replace("/signin");
  };

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
    ? "Your briefing is ready to read, export, and move into the rest of your work."
    : isFailed
      ? "We ran into an issue. You can start again or return to the workspace."
      : "Talven is turning the episode into a clean, readable briefing.";
  const isCached = job?.stage === "cached";
  const showProgressPanel = !hasMarkdown && !isComplete && !isFailed && !isCached;

  const statusFallbackStage = job?.status === "running" ? "summarizing" : job?.status ?? "queued";
  const rawStageKey = job?.stage ?? statusFallbackStage;
  const normalizedStage = rawStageKey === "completed" || rawStageKey === "cached" ? "rendering" : rawStageKey;
  const displayStageLabel = (() => {
    if (isComplete) return "Briefing ready";
    if (isFailed) return "Needs attention";
    switch (normalizedStage) {
      case "transcribing":
        return "Listening carefully";
      case "summarizing":
        return "Drafting the briefing";
      case "rendering":
        return "Polishing the output";
      default:
        return "Preparing your briefing";
    }
  })();

  const stageTone = isFailed ? chrome.statusPillDanger : isComplete ? chrome.statusPillSuccess : chrome.statusPillMuted;

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
    <div className={chrome.pageFrame}>
      <AppShellHeader active={null} remainingSeconds={null} accountLabel={getAccountLabel(user)} onSignOut={handleSignOut} />

      <main className={chrome.mainFrame}>
        <section className={chrome.heroBlock}>
          <div>
            <p className={chrome.heroEyebrow}>Briefing job</p>
            <h1 className={chrome.heroTitle}>{headline}</h1>
            <p className={chrome.heroText}>{subhead}</p>
          </div>
          <div className={chrome.heroMeta}>
            <span className={chrome.statusPill}>{displayStageLabel}</span>
            <span className={stageTone}>{isComplete ? "Final" : isFailed ? "Failed" : "Live"}</span>
            <span className={chrome.statusPillMuted}>Job {jobId.slice(0, 8)}</span>
          </div>
        </section>

        {showProgressPanel ? (
          <section className={`${chrome.surfaceStrong} ${styles.loadingCard}`}>
            <div className={styles.loadingTop}>
              <div>
                <h2 className={chrome.surfaceTitle}>Building your briefing</h2>
                <p className={chrome.surfaceText}>{job?.status_message ?? "Your briefing will appear here as soon as we have content."}</p>
              </div>
              <span className={chrome.statusPillMuted}>{clampedProgress}%</span>
            </div>

            <div className={chrome.progressTrack}>
              <div className={chrome.progressFill} style={{ width: `${clampedProgress}%` }} />
            </div>

            <div className={styles.loadingMeta}>
              <span>Usually a few minutes, depending on episode length.</span>
              <span>{displayStageLabel}</span>
            </div>

            <div className={chrome.stepList}>
              {[
                { key: "listen", label: "Listening", hint: "Transcribing the audio" },
                { key: "summarize", label: "Summarizing", hint: "Extracting the signal" },
                { key: "polish", label: "Polishing", hint: "Final structure and export readiness" }
              ].map((step, index) => {
                const activeIndex = normalizedStage === "rendering" ? 2 : normalizedStage === "summarizing" ? 1 : 0;
                const dotClass =
                  index < activeIndex
                    ? chrome.stepDotComplete
                    : index === activeIndex
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

            {error ? <div className={styles.errorCard}>{error}</div> : null}
          </section>
        ) : (
          <section className={chrome.readerLayout}>
            <article className={`${chrome.surfaceStrong} ${chrome.readerMain} ${styles.readerCard}`}>
              <div className={styles.readerHeader}>
                <div>
                  <h2 className={chrome.surfaceTitle}>Briefing</h2>
                  <p className={chrome.surfaceText}>
                    {isComplete
                      ? "Final Talven output, ready to read and export."
                      : "The document updates as the pipeline finishes the final pass."}
                  </p>
                </div>
                <span className={isComplete ? chrome.statusPillSuccess : chrome.statusPillMuted}>
                  {isComplete ? "Final" : "Updating"}
                </span>
              </div>

              {markdownToRender ? (
                <StreamingMarkdown
                  markdown={markdownToRender}
                  isStreaming={false}
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
                    <p className={chrome.surfaceText}>Save the finished brief or move back into the desk.</p>
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
                      onClick={handleGeneratePdf}
                      disabled={pdfLoading || !job?.summary_id}
                    >
                      {pdfLoading ? "Preparing PDF..." : "Generate PDF"}
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
                    <h2 className={chrome.surfaceTitle}>Job state</h2>
                    <p className={chrome.surfaceText}>Pipeline status and utility details for this briefing.</p>
                  </div>
                </div>
                <div className={styles.metaList}>
                  <div className={styles.metaRow}>
                    <span className={styles.metaLabel}>Stage</span>
                    <span className={styles.metaValue}>{displayStageLabel}</span>
                  </div>
                  <div className={styles.metaRow}>
                    <span className={styles.metaLabel}>Progress</span>
                    <span className={styles.metaValue}>{clampedProgress}%</span>
                  </div>
                  <div className={styles.metaRow}>
                    <span className={styles.metaLabel}>Summary ID</span>
                    <span className={styles.metaValue}>{summary?.summary_id ?? "Pending"}</span>
                  </div>
                </div>
                {job?.status_message ? <p className={chrome.subtleText}>{job.status_message}</p> : null}
              </div>

              {job?.status === "failed" ? (
                <div className={styles.errorCard}>Error: {job.error_message ?? "Job failed."}</div>
              ) : null}
              {error ? <div className={styles.errorCard}>{error}</div> : null}
            </aside>
          </section>
        )}
      </main>
    </div>
  );
}

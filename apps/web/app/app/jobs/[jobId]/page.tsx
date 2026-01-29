"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { JobStatusResponse, SummaryResponse } from "@fathom/api-client";
import { createApiClient, getApiBaseUrl } from "@fathom/api-client";
import styles from "../../app.module.css";
import { getApiErrorMessage } from "../../../lib/apiErrors";
import { getSupabaseClient } from "../../../lib/supabaseClient";

const POLL_INTERVAL_MS = 2000;
const SSE_STALL_TIMEOUT_MS = 6000;

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
  const [loading, setLoading] = useState(true);
  const [statusMessage, setStatusMessage] = useState<string>("Initializing job...");
  const [progress, setProgress] = useState(5);
  const [streamedMarkdown, setStreamedMarkdown] = useState("");
  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sseAbortRef = useRef<AbortController | null>(null);

  const stageFallback: Record<string, { progress: number; message: string }> = {
    queued: { progress: 8, message: "Queued — waiting for a worker" },
    running: { progress: 20, message: "Starting the summary job" },
    warming: { progress: 15, message: "Warming up the engines" },
    transcribing: { progress: 35, message: "Transcribing the audio" },
    checking_cache: { progress: 50, message: "Checking for existing summaries" },
    summarizing: { progress: 65, message: "Drafting your briefing" },
    rendering: { progress: 85, message: "Final polish in progress" },
    completed: { progress: 100, message: "Summary ready" },
    cached: { progress: 100, message: "Loaded from cache" },
    failed: { progress: 100, message: "Summary failed" }
  };

  const updateProgress = (payload: JobStatusResponse) => {
    if (typeof payload.progress === "number") {
      setProgress(payload.progress);
    } else if (payload.stage && stageFallback[payload.stage]) {
      setProgress(stageFallback[payload.stage].progress);
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

    if (payload.status_message) {
      setStatusMessage(payload.status_message);
    } else if (payload.stage && stageFallback[payload.stage]) {
      setStatusMessage(stageFallback[payload.stage].message);
    } else {
      setStatusMessage("Processing your summary...");
    }
  };

  const fetchSummary = async (summaryId: string, accessToken: string) => {
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
      setStreamedMarkdown((prev) =>
        summaryData.markdown && summaryData.markdown.length > prev.length ? summaryData.markdown : prev
      );
    }
  };

  const handleJobPayload = async (payload: JobStatusResponse, accessToken: string) => {
    setJob(payload);
    updateProgress(payload);

    if (payload.status === "succeeded" && payload.summary_id) {
      await fetchSummary(payload.summary_id, accessToken);
      setLoading(false);
      return true;
    }

    if (payload.status === "failed") {
      setLoading(false);
      return true;
    }

    return false;
  };

  const startPolling = (accessToken: string) => {
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
          setLoading(false);
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
        setLoading(false);
      }
    };

    void poll();
  };

  const startSse = async (accessToken: string) => {
    if (sseAbortRef.current) {
      return;
    }

    const controller = new AbortController();
    sseAbortRef.current = controller;

    let stallTimer: ReturnType<typeof setTimeout> | null = null;
    const resetStallTimer = () => {
      if (stallTimer) {
        clearTimeout(stallTimer);
      }
      stallTimer = setTimeout(() => {
        controller.abort();
        startPolling(accessToken);
      }, SSE_STALL_TIMEOUT_MS);
    };

    resetStallTimer();

    try {
      const response = await fetch(`${getApiBaseUrl()}/jobs/${jobId}/events`, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
          Accept: "text/event-stream"
        },
        signal: controller.signal
      });

      if (!response.ok || !response.body) {
        if (response.status === 429) {
          setStatusMessage("High traffic detected. Switching to polling...");
        }
        if (stallTimer) {
          clearTimeout(stallTimer);
        }
        startPolling(accessToken);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }

        resetStallTimer();
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";

        for (const chunk of chunks) {
          const lines = chunk.split("\n");
          let eventName = "message";
          const dataLines: string[] = [];

          for (const line of lines) {
            if (line.startsWith("event:")) {
              eventName = line.replace("event:", "").trim();
            } else if (line.startsWith("data:")) {
              dataLines.push(line.replace("data:", "").trim());
            }
          }

          const dataPayload = dataLines.join("\n");

          if (eventName === "job") {
            try {
              const payload = JSON.parse(dataPayload) as JobStatusResponse;
              const done = await handleJobPayload(payload, accessToken);
              if (done) {
                reader.cancel();
                return;
              }
            } catch (err) {
              setError(err instanceof Error ? err.message : "Failed to parse SSE payload.");
            }
          } else if (eventName === "summary" && dataPayload) {
            try {
              const parsed = JSON.parse(dataPayload) as { text?: string; delta?: string; markdown?: string };
              if (parsed.markdown) {
                setStreamedMarkdown(parsed.markdown);
              } else if (parsed.text || parsed.delta) {
                setStreamedMarkdown((prev) => `${prev}${parsed.text ?? parsed.delta ?? ""}`);
              }
            } catch {
              setStreamedMarkdown((prev) => `${prev}${dataPayload}`);
            }
          } else if (dataPayload) {
            setStreamedMarkdown((prev) => `${prev}${dataPayload}`);
          }
        }
      }
    } catch (err) {
      if ((err as { name?: string }).name !== "AbortError") {
        setError(err instanceof Error ? err.message : "SSE connection failed.");
      }
      startPolling(accessToken);
    } finally {
      if (stallTimer) {
        clearTimeout(stallTimer);
      }
    }
  };

  useEffect(() => {
    if (!jobId) {
      return;
    }

    const init = async () => {
      try {
        const supabase = getSupabaseClient();
        const { data: sessionData } = await supabase.auth.getSession();

        if (!sessionData.session) {
          router.replace("/signin");
          return;
        }

        await startSse(sessionData.session.access_token);
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
      if (sseAbortRef.current) {
        sseAbortRef.current.abort();
        sseAbortRef.current = null;
      }
    };
  }, [jobId, router]);

  const statusLabel = job?.stage ?? job?.status ?? "queued";
  const statusLabelText = statusLabel.replace(/_/g, " ");
  const markdownToRender =
    streamedMarkdown.length >= (summary?.markdown?.length ?? 0) ? streamedMarkdown : summary?.markdown ?? "";

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
          <Link className={styles.button} href="/app">
            Back to app
          </Link>
          <Link className={styles.button} href="/">
            Landing
          </Link>
        </div>
      </header>

      <main className={styles.main}>
        <div className={styles.card}>
          <div className={styles.statusRow}>
            <div>
              <h1 className={styles.cardTitle}>Summary in progress</h1>
              <p className={styles.cardText}>Job ID: {jobId}</p>
            </div>
            <span className={styles.statusBadge}>{statusLabelText}</span>
          </div>
          <div className={styles.progressWrap}>
            <div className={styles.progressTrack}>
              <div className={styles.progressFill} style={{ width: `${progress}%` }} />
            </div>
            <div className={styles.statusMessage}>{statusMessage}</div>
          </div>
          {job?.status === "failed" ? (
            <p className={styles.status}>Error: {job.error_message ?? "Job failed."}</p>
          ) : null}
          {loading ? <p className={styles.status}>We will keep this open and stream updates live.</p> : null}
          {error ? <p className={styles.status}>{error}</p> : null}
        </div>

        <div className={styles.card}>
          <h2 className={styles.summaryTitle}>Summary</h2>
          {markdownToRender ? (
            <>
              <div className={styles.markdown}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdownToRender}</ReactMarkdown>
                {job?.status === "running" && streamedMarkdown ? (
                  <span className={styles.streamingCursor} aria-hidden="true" />
                ) : null}
              </div>
              <div className={styles.summaryActions}>
                {pdfUrl ? (
                  <a className={styles.secondaryButton} href={pdfUrl} target="_blank" rel="noreferrer">
                    Download PDF
                  </a>
                ) : (
                  <button
                    className={styles.secondaryButton}
                    type="button"
                    onClick={handleGeneratePdf}
                    disabled={pdfLoading}
                  >
                    {pdfLoading ? "Preparing PDF..." : "Generate PDF"}
                  </button>
                )}
                <Link className={styles.secondaryButton} href="/app">
                  New summary
                </Link>
              </div>
              {pdfError ? <p className={styles.status}>{pdfError}</p> : null}
            </>
          ) : (
            <p className={styles.cardText}>
              {job?.status === "succeeded"
                ? "Summary ready, but still loading."
                : "Your summary will appear here once the job completes."}
            </p>
          )}
        </div>
      </main>
    </div>
  );
}

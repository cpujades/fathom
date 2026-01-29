"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { JobStatusResponse, SummaryResponse } from "@fathom/api-client";
import { createApiClient } from "@fathom/api-client";
import styles from "../../app.module.css";
import { getApiErrorMessage } from "../../../lib/apiErrors";
import { getSupabaseClient } from "../../../lib/supabaseClient";

const POLL_INTERVAL_MS = 2000;

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

  useEffect(() => {
    if (!jobId) {
      return;
    }

    let isActive = true;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const pollJob = async () => {
      try {
        const supabase = getSupabaseClient();
        const { data: sessionData } = await supabase.auth.getSession();

        if (!sessionData.session) {
          router.replace("/signin");
          return;
        }

        const api = createApiClient(sessionData.session.access_token);
        const { data, error: apiError } = await api.GET("/jobs/{job_id}", {
          params: {
            path: {
              job_id: jobId
            }
          }
        });

        if (apiError) {
          setError(getApiErrorMessage(apiError, "Unable to fetch job status."));
          setLoading(false);
          return;
        }

        if (data && isActive) {
          setJob(data);
        }

        if (data?.status === "succeeded" && data.summary_id) {
          const { data: summaryData, error: summaryError } = await api.GET(
            "/summaries/{summary_id}",
            {
              params: {
                path: {
                  summary_id: data.summary_id
                }
              }
            }
          );

          if (summaryError) {
            setError(getApiErrorMessage(summaryError, "Unable to fetch summary."));
          } else if (summaryData) {
            setSummary(summaryData);
            setPdfUrl(summaryData.pdf_url ?? null);
          }

          setLoading(false);
          return;
        }

        if (data?.status === "failed") {
          setLoading(false);
          return;
        }

        if (isActive) {
          timeoutId = setTimeout(pollJob, POLL_INTERVAL_MS);
        }
      } catch (err) {
        if (isActive) {
          setError(err instanceof Error ? err.message : "Something went wrong.");
          setLoading(false);
        }
      }
    };

    void pollJob();

    return () => {
      isActive = false;
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [jobId, router]);

  const statusLabel = job?.status ?? "queued";

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
            <span className={styles.statusBadge}>{statusLabel}</span>
          </div>
          {job?.status === "failed" ? (
            <p className={styles.status}>Error: {job.error_message ?? "Job failed."}</p>
          ) : null}
          {loading ? <p className={styles.status}>Checking status every few seconds.</p> : null}
          {error ? <p className={styles.status}>{error}</p> : null}
        </div>

        <div className={styles.card}>
          <h2 className={styles.summaryTitle}>Summary</h2>
          {summary ? (
            <>
              <div className={styles.markdown}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{summary.markdown}</ReactMarkdown>
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

"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { createApiClient } from "@fathom/api-client";

import { AppShellHeader } from "../../../components/AppShellHeader";
import chrome from "../../../components/app-chrome.module.css";
import styles from "../[jobId]/job.module.css";
import { getApiErrorMessage } from "../../../lib/apiErrors";
import { getSupabaseClient } from "../../../lib/supabaseClient";

function JobCreatePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) {
      return;
    }
    startedRef.current = true;

    const run = async () => {
      const rawUrl = searchParams.get("url")?.trim();
      if (!rawUrl) {
        setError("Missing URL. Head back and try again.");
        return;
      }

      try {
        const supabase = getSupabaseClient();
        const { data: sessionData, error: sessionError } = await supabase.auth.getSession();

        if (sessionError || !sessionData.session) {
          router.replace("/signin");
          return;
        }

        const api = createApiClient(sessionData.session.access_token);
        const { data, error: apiError } = await api.POST("/summarize", {
          body: {
            url: rawUrl
          }
        });

        if (apiError) {
          setError(getApiErrorMessage(apiError, "Unable to create a briefing job."));
          return;
        }

        if (data?.job_id) {
          router.replace(`/app/jobs/${data.job_id}`);
          return;
        }

        setError("Unexpected response from the server.");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      }
    };

    void run();
  }, [router, searchParams]);

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader active={null} remainingSeconds={null} accountLabel={null} />

      <main className={chrome.mainFrame}>
        <section className={chrome.heroBlock}>
          <div>
            <p className={chrome.heroEyebrow}>Briefing job</p>
            <h1 className={chrome.heroTitle}>Starting your briefing</h1>
            <p className={chrome.heroText}>We’re creating the job and moving you into the live progress view.</p>
          </div>
          <div className={chrome.heroActions}>
            <Link className={chrome.ghostButton} href="/app">
              Back to workspace
            </Link>
          </div>
        </section>

        <section className={`${chrome.surfaceStrong} ${styles.loadingCard}`}>
          <div className={styles.loadingTop}>
            <div>
              <h2 className={chrome.surfaceTitle}>Connecting to the pipeline</h2>
              <p className={chrome.surfaceText}>This should take just a moment.</p>
            </div>
            <span className={chrome.statusPillMuted}>Starting</span>
          </div>

          <div className={chrome.progressTrack}>
            <div className={chrome.progressFill} style={{ width: "12%" }} />
          </div>

          <div className={chrome.stepList}>
            <div className={chrome.stepRow}>
              <span className={chrome.stepDotActive} />
              <div>
                <p className={chrome.stepLabel}>Queueing the request</p>
                <p className={chrome.stepHint}>Talven is registering the episode and preparing the job.</p>
              </div>
            </div>
          </div>

          {error ? <div className={styles.errorCard}>{error}</div> : null}
        </section>
      </main>
    </div>
  );
}

export default function JobCreatePage() {
  return (
    <Suspense
      fallback={
        <div className={chrome.pageFrame}>
          <AppShellHeader active={null} remainingSeconds={null} accountLabel={null} />
          <main className={chrome.mainFrame}>
            <section className={`${chrome.surfaceStrong} ${styles.loadingCard}`}>
              <div className={styles.loadingTop}>
                <div>
                  <h2 className={chrome.surfaceTitle}>Starting your briefing</h2>
                  <p className={chrome.surfaceText}>Preparing request details.</p>
                </div>
              </div>
            </section>
          </main>
        </div>
      }
    >
      <JobCreatePageContent />
    </Suspense>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { createApiClient } from "@fathom/api-client";
import styles from "../[jobId]/job.module.css";
import { getApiErrorMessage } from "../../../lib/apiErrors";
import { getSupabaseClient } from "../../../lib/supabaseClient";

export default function JobCreatePage() {
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
          setError(getApiErrorMessage(apiError, "Unable to create a summary job."));
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
            <h1 className={styles.heroTitle}>Starting your briefing</h1>
            <p className={styles.heroText}>We’re creating the job and will move you into the live progress view.</p>
          </section>

          <section className={styles.loadingSection}>
            <div className={styles.loadingCard}>
              <div className={styles.loadingTop}>
                <span className={styles.spinner} aria-hidden="true" />
                <div>
                  <h2 className={styles.loadingTitle}>Connecting to the pipeline</h2>
                  <p className={styles.loadingSubtitle}>This should take just a moment.</p>
                </div>
              </div>

              <div className={styles.progressTrack}>
                <div className={styles.progressFill} style={{ width: "12%" }} />
              </div>

              {error ? <div className={styles.errorCard}>{error}</div> : null}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

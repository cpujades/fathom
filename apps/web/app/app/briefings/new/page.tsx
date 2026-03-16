"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { createApiClient } from "@fathom/api-client";

import { AppShellHeader } from "../../../components/AppShellHeader";
import { useAppShell } from "../../../components/AppShellProvider";
import chrome from "../../../components/app-chrome.module.css";
import { getApiErrorMessage } from "../../../lib/apiErrors";
import { getAccountLabel } from "../../../lib/accountLabel";
import { cacheSessionSnapshot, invalidateBriefingsCache } from "../../../lib/appDataCache";
import styles from "../session.module.css";

function BriefingCreatePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { accessToken, loading, remainingSeconds, signOut, user } = useAppShell();
  const [error, setError] = useState<string | null>(null);
  const startedRef = useRef(false);

  useEffect(() => {
    if (loading || startedRef.current) {
      return;
    }
    if (!accessToken) {
      router.replace("/signin");
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
        const api = createApiClient(accessToken);
        const { data, error: apiError } = await api.POST("/briefing-sessions", {
          body: {
            url: rawUrl
          }
        });

        if (apiError) {
          setError(getApiErrorMessage(apiError, "Unable to start the briefing."));
          return;
        }

        if (data?.session_id) {
          cacheSessionSnapshot(data);
          if (data.resolution_type === "reused_ready") {
            invalidateBriefingsCache();
          }
          router.replace(`/app/briefings/sessions/${data.session_id}`);
          return;
        }

        setError("Unexpected response from the server.");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      }
    };

    void run();
  }, [accessToken, loading, router, searchParams]);

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader
        active={null}
        remainingSeconds={remainingSeconds}
        accountLabel={getAccountLabel(user)}
        onSignOut={signOut}
      />

      <main className={chrome.mainFrame}>
        <section className={chrome.heroBlock}>
          <div>
            <p className={chrome.heroEyebrow}>Briefing</p>
            <h1 className={chrome.heroTitle}>Starting your briefing</h1>
            <p className={chrome.heroText}>Talven is opening a live session and checking for reusable work first.</p>
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
              <h2 className={chrome.surfaceTitle}>Creating your session</h2>
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
                <p className={chrome.stepLabel}>Opening a session</p>
                <p className={chrome.stepHint}>Talven is validating the source and connecting you to live updates.</p>
              </div>
            </div>
          </div>

          {error ? (
            <div className={styles.errorCard}>
              <p>{error}</p>
              {isCreditError(error) ? (
                <div className={chrome.actionRow}>
                  <Link className={chrome.primaryButton} href="/app/billing#billing-offers">
                    Get more listening time
                  </Link>
                </div>
              ) : null}
            </div>
          ) : null}
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
          <main className={chrome.mainFrame}>
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

function isCreditError(message: string): boolean {
  const normalized = message.toLowerCase();
  return normalized.includes("insufficient credits") || normalized.includes("no remaining credits");
}

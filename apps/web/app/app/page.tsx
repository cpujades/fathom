"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { UsageOverviewResponse } from "@fathom/api-client";
import type { User } from "@supabase/supabase-js";
import { createApiClient } from "@fathom/api-client";

import { AppShellHeader } from "../components/AppShellHeader";
import chrome from "../components/app-chrome.module.css";
import { getApiErrorMessage } from "../lib/apiErrors";
import { getAccountLabel } from "../lib/accountLabel";
import { getSupabaseClient } from "../lib/supabaseClient";
import styles from "./home.module.css";

function getFirstName(user: Pick<User, "user_metadata"> | null): string | null {
  const fullName =
    (user?.user_metadata?.full_name as string | undefined) ?? (user?.user_metadata?.name as string | undefined);

  if (!fullName) {
    return null;
  }

  const firstName = fullName
    .trim()
    .split(/\s+/)
    .find(Boolean);

  return firstName && firstName.length > 0 ? firstName : null;
}

export default function AppHome() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [usage, setUsage] = useState<UsageOverviewResponse | null>(null);

  useEffect(() => {
    let unsubscribe: (() => void) | null = null;

    const loadSession = async () => {
      try {
        router.prefetch("/app/jobs/new");
        const supabase = getSupabaseClient();
        const { data: sessionData, error: sessionError } = await supabase.auth.getSession();

        if (sessionError) {
          setError(sessionError.message);
        }

        if (!sessionData.session) {
          router.replace("/signin");
          return;
        }

        setUser(sessionData.session.user);

        const api = createApiClient(sessionData.session.access_token);
        const { data: usageData, error: usageError } = await api.GET("/billing/usage");

        if (usageError) {
          setError(getApiErrorMessage(usageError, "Unable to load usage."));
        } else {
          setUsage(usageData ?? null);
        }

        const { data: authListener } = supabase.auth.onAuthStateChange((_event, authSession) => {
          if (!authSession) {
            router.replace("/signin");
          } else {
            setUser(authSession.user);
          }
        });

        unsubscribe = () => authListener.subscription.unsubscribe();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      } finally {
        setLoading(false);
      }
    };

    void loadSession();

    return () => {
      unsubscribe?.();
    };
  }, [router]);

  const handleSignOut = async () => {
    const supabase = getSupabaseClient();
    await supabase.auth.signOut();
    router.replace("/signin");
  };

  const handleSubmit = () => {
    if (submitting) {
      return;
    }

    if (!url.trim()) {
      setError("Paste a valid podcast or YouTube URL to start a briefing.");
      return;
    }

    setError(null);
    setSubmitting(true);
    router.push(`/app/jobs/new?url=${encodeURIComponent(url.trim())}`);
  };

  const firstName = getFirstName(user);
  const workspaceTitle = loading
    ? "Loading your desk..."
    : firstName
      ? `Which podcast is worth a deeper read, ${firstName}?`
      : "Which podcast is worth a deeper read?";

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader
        active="home"
        remainingSeconds={usage?.total_remaining_seconds ?? null}
        accountLabel={getAccountLabel(user)}
        onSignOut={handleSignOut}
      />

      <main className={chrome.mainFrame}>
        <section className={styles.workspaceShell}>
          <article className={`${chrome.surfaceStrong} ${styles.workspacePanel}`}>
            <h1 className={styles.workspaceTitle}>{workspaceTitle}</h1>

            <div className={styles.commandBlock}>
              <div className={styles.commandRow}>
                <div className={styles.commandField}>
                  <input
                    className={`${chrome.input} ${styles.commandInput}`}
                    type="url"
                    placeholder="https://www.youtube.com/watch?v=..."
                    aria-label="Podcast or YouTube URL"
                    value={url}
                    onChange={(event) => setUrl(event.target.value)}
                    disabled={loading}
                  />
                </div>
                <div className={styles.commandActions}>
                  <button
                    className={`${chrome.primaryButton} ${styles.commandButton}`}
                    type="button"
                    onClick={handleSubmit}
                    disabled={loading || submitting}
                  >
                    {submitting ? "Starting..." : "Start briefing"}
                  </button>
                </div>
              </div>
              {error ? <p className={`${chrome.inlineStatus} ${chrome.inlineStatusError}`}>{error}</p> : null}
            </div>
          </article>
        </section>
      </main>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { User } from "@supabase/supabase-js";

import { AppShellHeader } from "../components/AppShellHeader";
import { useAppShell } from "../components/AppShellProvider";
import chrome from "../components/app-chrome.module.css";
import { getAccountLabel } from "../lib/accountLabel";
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
  const { loading, remainingSeconds, signOut, user } = useAppShell();
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    router.prefetch("/app/briefings/new");
  }, [router]);

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
    router.push(`/app/briefings/new?url=${encodeURIComponent(url.trim())}`);
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
        remainingSeconds={remainingSeconds}
        accountLabel={getAccountLabel(user)}
        onSignOut={signOut}
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

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { User } from "@supabase/supabase-js";
import { createApiClient } from "@fathom/api-client";

import styles from "./app.module.css";
import { getSupabaseClient } from "../lib/supabaseClient";

export default function AppHome() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [healthStatus, setHealthStatus] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let unsubscribe: (() => void) | null = null;

    const loadSession = async () => {
      try {
        router.prefetch("/app/jobs/new");
        const supabase = getSupabaseClient();
        const { data, error: sessionError } = await supabase.auth.getSession();
        if (sessionError) {
          setError(sessionError.message);
        }

        if (!data.session) {
          router.replace("/signin");
          return;
        }

        setUser(data.session.user);

        const api = createApiClient();
        const { data: healthData } = await api.GET("/meta/health");
        setHealthStatus(healthData?.status ?? null);

        const { data: authListener } = supabase.auth.onAuthStateChange((_event, session) => {
          if (!session) {
            router.replace("/signin");
          } else {
            setUser(session.user);
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
      setError("Please paste a valid podcast or YouTube URL.");
      return;
    }

    setError(null);
    setSubmitting(true);

    const trimmedUrl = url.trim();
    router.push(`/app/jobs/new?url=${encodeURIComponent(trimmedUrl)}`);
  };

  if (loading) {
    return (
      <div className={styles.page}>
        <header className={styles.header}>
          <div className={styles.brand}>
            <span className={styles.brandMark} aria-hidden="true" />
            Fathom
          </div>
        </header>
        <main className={styles.main}>
          <div className={styles.card}>
            <h1 className={styles.cardTitle}>Loading your workspace...</h1>
            <p className={styles.cardText}>Hang tight while we restore your session.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true" />
          Fathom
        </div>
        <div className={styles.headerActions}>
          {healthStatus ? <div className={styles.usageChip}>API: {healthStatus}</div> : null}
          {user?.email ? <div className={styles.usageChip}>{user.email}</div> : null}
          <div className={styles.usageChip}>Usage: 0 / 6h</div>
          <Link className={styles.button} href="/">
            Landing
          </Link>
          <button className={styles.button} onClick={handleSignOut} type="button">
            Sign out
          </button>
        </div>
      </header>

      <main className={styles.main}>
        <div className={styles.card}>
          <h1 className={styles.cardTitle}>Welcome{user?.email ? `, ${user.email}` : ""}</h1>
          <p className={styles.cardText}>Paste a podcast or YouTube link to get started.</p>
          <div className={styles.inputRow}>
            <input
              className={styles.input}
              type="url"
              placeholder="https://www.youtube.com/watch?v=..."
              aria-label="Podcast or YouTube URL"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
            />
            <button className={styles.primaryButton} type="button" onClick={handleSubmit} disabled={submitting}>
              {submitting ? "Submitting..." : "Summarize"}
            </button>
          </div>
          <p className={styles.inputHelp}>
            We will transcribe, summarize, and format the briefing automatically.
          </p>
          {error ? <p className={styles.status}>{error}</p> : null}
        </div>
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>Your briefings</h2>
          <p className={styles.cardText}>No summaries yet. Your next one will show up here.</p>
        </div>
      </main>
    </div>
  );
}

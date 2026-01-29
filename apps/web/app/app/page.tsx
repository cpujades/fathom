"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { User } from "@supabase/supabase-js";

import styles from "./app.module.css";
import { getSupabaseClient } from "../lib/supabaseClient";

export default function AppHome() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let unsubscribe: (() => void) | null = null;

    const loadSession = async () => {
      try {
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
            />
            <button className={styles.primaryButton} type="button">
              Summarize
            </button>
          </div>
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

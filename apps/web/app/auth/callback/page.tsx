"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import styles from "../auth.module.css";
import { getSupabaseClient } from "../../lib/supabaseClient";

function AuthCallbackPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [message, setMessage] = useState("Finalizing your session...");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const finalize = async () => {
      const errorParam = searchParams.get("error");
      const errorDescription = searchParams.get("error_description");
      const code = searchParams.get("code");

      if (errorParam) {
        setError(errorDescription || "Authentication failed.");
        setMessage("");
        return;
      }

      try {
        const supabase = getSupabaseClient();

        if (code) {
          const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
          if (exchangeError) {
            setError(exchangeError.message);
            setMessage("");
            return;
          }
        }

        const { data } = await supabase.auth.getSession();
        if (data.session) {
          router.replace("/app");
          return;
        }

        setError("No active session found. Please sign in again.");
        setMessage("");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
        setMessage("");
      }
    };

    void finalize();
  }, [router, searchParams]);

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true" />
          Fathom
        </div>
        <div>
          <h1 className={styles.title}>Signing you in</h1>
          <p className={styles.subtitle}>{message}</p>
        </div>
        {error ? <div className={styles.error}>{error}</div> : null}
      </div>
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className={styles.page}>
          <div className={styles.card}>
            <div className={styles.brand}>
              <span className={styles.brandMark} aria-hidden="true" />
              Fathom
            </div>
            <div>
              <h1 className={styles.title}>Signing you in</h1>
              <p className={styles.subtitle}>Finalizing your session...</p>
            </div>
          </div>
        </div>
      }
    >
      <AuthCallbackPageContent />
    </Suspense>
  );
}

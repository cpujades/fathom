"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import styles from "../auth/auth.module.css";
import { mapAuthError } from "../lib/authErrors";
import { getSupabaseClient } from "../lib/supabaseClient";
import { getSiteUrl } from "../lib/url";

export default function SignInPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"password" | "magic">("password");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSignIn = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setLoading(true);

    try {
      const supabase = getSupabaseClient();
      if (mode === "magic") {
        const { error: otpError } = await supabase.auth.signInWithOtp({
          email,
          options: {
            emailRedirectTo: `${getSiteUrl()}/auth/callback`,
            shouldCreateUser: false
          }
        });

        if (otpError) {
          setError(mapAuthError(otpError, "Unable to send a magic link."));
        } else {
          setMessage("Check your inbox for a sign-in link.");
        }
        return;
      }

      const { error: signInError } = await supabase.auth.signInWithPassword({
        email,
        password
      });

      if (signInError) {
        setError(mapAuthError(signInError, "Unable to sign you in."));
      } else {
        router.replace("/app");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async () => {
    setError(null);
    setMessage(null);

    if (!email.trim()) {
      setError("Please enter your email to reset your password.");
      return;
    }

    setLoading(true);

    try {
      const supabase = getSupabaseClient();
      const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${getSiteUrl()}/auth/callback`
      });

      if (resetError) {
        setError(mapAuthError(resetError, "Unable to send a reset link."));
      } else {
        setMessage("If an account exists for this email, check your inbox for a reset link.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  const handleGoogle = async () => {
    setError(null);
    setMessage(null);
    setLoading(true);

    try {
      const supabase = getSupabaseClient();
      const { error: oauthError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: `${getSiteUrl()}/auth/callback`
        }
      });

      if (oauthError) {
        setError(mapAuthError(oauthError, "Unable to continue with Google."));
        setLoading(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setLoading(false);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true" />
          Fathom
        </div>

        <div>
          <h1 className={styles.title}>Welcome back</h1>
          <p className={styles.subtitle}>Sign in to continue building your briefing library.</p>
        </div>

        {error ? <div className={styles.error}>{error}</div> : null}
        {message ? <div className={styles.notice}>{message}</div> : null}

      <form className={styles.form} onSubmit={handleSignIn}>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="email">
            Email
          </label>
          <input
              className={styles.input}
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@company.com"
            required
          />
        </div>

        {mode === "password" ? (
          <div className={styles.field}>
            <label className={styles.label} htmlFor="password">
              Password
            </label>
            <input
              className={styles.input}
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
              required
            />
          </div>
        ) : null}

        <div className={styles.actions}>
          <button className={`${styles.button} ${styles.buttonPrimary}`} type="submit" disabled={loading}>
            {loading
              ? "Working..."
              : mode === "magic"
                ? "Email me a sign-in link"
                : "Sign in"}
          </button>
        </div>

        {mode === "password" ? (
          <div className={styles.modeToggle}>
            <button className={styles.linkButton} type="button" onClick={handleResetPassword} disabled={loading}>
              Forgot password?
            </button>
          </div>
        ) : null}

        <div className={styles.modeToggle}>
          {mode === "magic" ? "Prefer a password?" : "Prefer a magic link?"}
          <button
            type="button"
            className={styles.linkButton}
            onClick={() => setMode(mode === "magic" ? "password" : "magic")}
            disabled={loading}
          >
            {mode === "magic" ? "Use password" : "Use magic link"}
          </button>
        </div>
      </form>

        <div className={styles.divider}>or</div>

        <button className={`${styles.button} ${styles.buttonGhost}`} onClick={handleGoogle} disabled={loading}>
          <Image
            className={styles.googleIcon}
            src="/google-logo.webp"
            alt=""
            aria-hidden="true"
            width={18}
            height={18}
          />
          Continue with Google
        </button>

        <div className={styles.links}>
          <span>
            New here? <Link href="/signup">Create an account</Link>
          </span>
          <Link href="/">Back to home</Link>
        </div>
      </div>
    </div>
  );
}

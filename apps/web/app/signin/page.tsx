"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import styles from "../auth/auth.module.css";
import { mapAuthError } from "../lib/authErrors";
import { getSupabaseClient } from "../lib/supabaseClient";
import { buildAuthCallbackUrl, buildSignUpPath, getSafeNextPath } from "../lib/url";

export default function SignInPage() {
  const router = useRouter();

  const [nextPath, setNextPath] = useState("/app");
  const [intent, setIntent] = useState<string | null>(null);
  const [plan, setPlan] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setNextPath(getSafeNextPath(params.get("next")));
    setIntent(params.get("intent"));
    setPlan(params.get("plan"));
    setError(params.get("auth_error"));
  }, []);

  const callbackUrl = useMemo(() => {
    return buildAuthCallbackUrl(nextPath);
  }, [nextPath]);

  const signUpHref = useMemo(() => {
    return buildSignUpPath(nextPath, {
      intent,
      plan
    });
  }, [intent, nextPath, plan]);

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
            emailRedirectTo: callbackUrl,
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
        router.replace(nextPath);
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
        redirectTo: callbackUrl
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
          redirectTo: callbackUrl
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
      <div className={styles.shell}>
        <aside className={styles.panel}>
          <div className={styles.brand}>
            <span className={styles.brandMark} aria-hidden="true" />
            Talven
          </div>
          <h1 className={styles.panelTitle}>Welcome back</h1>
          <p className={styles.panelText}>Sign in to resume your briefings and keep your edge close at hand.</p>
          <ul className={styles.panelList}>
            <li>Billing controls when you need more time</li>
            <li>Your briefings and reserve balance in one place</li>
            <li>Structured briefings ready to export</li>
          </ul>
          <p className={styles.panelFooter}>Need a new account? Create one in under a minute.</p>
        </aside>

        <section className={styles.card}>
          <div>
            <h2 className={styles.title}>Sign in</h2>
            <p className={styles.subtitle}>Use password or magic link. Google sign-in is also available.</p>
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
                  placeholder="Your password"
                  required
                />
              </div>
            ) : null}

            <div className={styles.actions}>
              <button className={`${styles.button} ${styles.buttonPrimary}`} type="submit" disabled={loading}>
                {loading ? "Working..." : mode === "magic" ? "Email sign-in link" : "Sign in"}
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
            <Image className={styles.googleIcon} src="/google-logo.webp" alt="" aria-hidden="true" width={18} height={18} />
            Continue with Google
          </button>

          <div className={styles.links}>
            <span>
              New here? <Link href={signUpHref}>Create an account</Link>
            </span>
            <Link href="/">Return to Talven</Link>
          </div>
        </section>
      </div>
    </div>
  );
}

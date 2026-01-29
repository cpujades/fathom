"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import styles from "../auth/auth.module.css";
import { mapAuthError } from "../lib/authErrors";
import { getSupabaseClient } from "../lib/supabaseClient";
import { getSiteUrl } from "../lib/url";

export default function SignUpPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [mode, setMode] = useState<"password" | "magic">("password");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSignUp = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setMessage(null);
    try {
      if (!email.trim()) {
        setError("Please enter your email.");
        return;
      }

      if (mode === "password") {
        if (!password || password.length < 12 || !/\d/.test(password)) {
          setError("Password must be at least 12 characters and include a number.");
          return;
        }
      }

      if (!firstName.trim() || !lastName.trim()) {
        setError("Please enter your first and last name.");
        return;
      }

      const fullName = `${firstName.trim()} ${lastName.trim()}`.trim();

      setLoading(true);
      const supabase = getSupabaseClient();
      if (mode === "magic") {
        const { error: otpError } = await supabase.auth.signInWithOtp({
          email,
          options: {
            emailRedirectTo: `${getSiteUrl()}/auth/callback`,
            shouldCreateUser: true,
            data: {
              full_name: fullName,
              first_name: firstName.trim(),
              last_name: lastName.trim()
            }
          }
        });

        if (otpError) {
          setError(mapAuthError(otpError, "Unable to send a sign-up link."));
        } else {
          setMessage("If an account exists for this email, check your inbox for a sign-in link.");
        }
        return;
      }

      const { data, error: signUpError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: `${getSiteUrl()}/auth/callback`,
          data: {
            full_name: fullName,
            first_name: firstName.trim(),
            last_name: lastName.trim()
          }
        }
      });

      if (signUpError) {
        setError(mapAuthError(signUpError, "Unable to create your account."));
      } else if (data.user && Array.isArray(data.user.identities) && data.user.identities.length === 0) {
        setError("An account with this email already exists. Try signing in instead.");
      } else if (data.session) {
        router.replace("/app");
      } else {
        setMessage(
          "Check your inbox to confirm your email."
        );
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
          <h1 className={styles.title}>Create your account</h1>
          <p className={styles.subtitle}>Start summarizing podcasts in seconds.</p>
        </div>

        {error ? <div className={styles.error}>{error}</div> : null}
        {message ? <div className={styles.notice}>{message}</div> : null}

        <form className={styles.form} onSubmit={handleSignUp}>
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
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="12+ characters with a number"
                required
              />
            </div>
          ) : null}

          <div className={styles.field}>
            <label className={styles.label} htmlFor="firstName">
              First name
            </label>
            <input
              className={styles.input}
              id="firstName"
              type="text"
              autoComplete="given-name"
              value={firstName}
              onChange={(event) => setFirstName(event.target.value)}
              placeholder="Ada"
              required
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="lastName">
              Last name
            </label>
            <input
              className={styles.input}
              id="lastName"
              type="text"
              autoComplete="family-name"
              value={lastName}
              onChange={(event) => setLastName(event.target.value)}
              placeholder="Lovelace"
              required
            />
          </div>

          <div className={styles.actions}>
            <button className={`${styles.button} ${styles.buttonPrimary}`} type="submit" disabled={loading}>
              {loading
                ? "Working..."
                : mode === "magic"
                  ? "Email me a sign-up link"
                  : "Create account"}
            </button>
          </div>

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

        <button
          className={`${styles.button} ${styles.buttonGhost}`}
          onClick={handleGoogle}
          disabled={loading}
        >
          <img className={styles.googleIcon} src="/google-logo.webp" alt="" aria-hidden="true" />
          Continue with Google
        </button>

        <div className={styles.links}>
          <span>
            Already have an account? <Link href="/signin">Sign in</Link>
          </span>
          <Link href="/">Back to home</Link>
        </div>
      </div>
    </div>
  );
}

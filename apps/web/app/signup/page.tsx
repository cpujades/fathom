"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import styles from "../auth/auth.module.css";
import { mapAuthCallbackErrorCode, mapAuthError } from "../lib/authErrors";
import { getSupabaseClient } from "../lib/supabaseClient";
import { buildAuthCallbackUrl, buildSignInPath, getSafeNextPath } from "../lib/url";

export default function SignUpPage() {
  const router = useRouter();

  const [nextPath, setNextPath] = useState("/app");
  const [intent, setIntent] = useState<string | null>(null);
  const [plan, setPlan] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setNextPath(getSafeNextPath(params.get("next")));
    setIntent(params.get("intent"));
    setPlan(params.get("plan"));
    setError(mapAuthCallbackErrorCode(params.get("auth_error")));
  }, []);

  const callbackUrl = useMemo(() => {
    return buildAuthCallbackUrl(nextPath);
  }, [nextPath]);

  const signInHref = useMemo(() => {
    return buildSignInPath(nextPath, {
      intent,
      plan
    });
  }, [intent, nextPath, plan]);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [mode, setMode] = useState<"password" | "magic">("magic");
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

      if (mode === "password" && (!password || password.length < 12 || !/\d/.test(password))) {
        setError("Password must be at least 12 characters and include a number.");
        return;
      }

      const fullName = `${firstName.trim()} ${lastName.trim()}`.trim();
      const profileData: {
        full_name?: string;
        first_name?: string;
        last_name?: string;
      } = {};
      if (firstName.trim()) {
        profileData.first_name = firstName.trim();
      }
      if (lastName.trim()) {
        profileData.last_name = lastName.trim();
      }
      if (fullName) {
        profileData.full_name = fullName;
      }

      setLoading(true);
      const supabase = getSupabaseClient();

      if (mode === "magic") {
        const { error: otpError } = await supabase.auth.signInWithOtp({
          email,
          options: {
            emailRedirectTo: callbackUrl,
            shouldCreateUser: true,
            data: profileData
          }
        });

        if (otpError) {
          setError(mapAuthError(otpError, "Unable to send a sign-up link."));
        } else {
          setMessage("Check your inbox to continue with account creation.");
        }
        return;
      }

      const { data, error: signUpError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: callbackUrl,
          data: profileData
        }
      });

      if (signUpError) {
        setError(mapAuthError(signUpError, "Unable to create your account."));
      } else if (data.user && Array.isArray(data.user.identities) && data.user.identities.length === 0) {
        setError("An account with this email already exists. Try signing in instead.");
      } else if (data.session) {
        router.replace(nextPath);
      } else {
        setMessage("Check your inbox to confirm your email.");
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
          <h1 className={styles.panelTitle}>Create your account</h1>
          <p className={styles.panelText}>Turn long-form audio into concise, actionable briefings built for private advantage.</p>
          <ul className={styles.panelList}>
            <li>Begin with included monthly usage</li>
            <li>Upgrade or top up when listening expands</li>
            <li>Track usage and exports in one workspace</li>
          </ul>
          <p className={styles.panelFooter}>Already have an account? Sign in and continue where you left off.</p>
        </aside>

        <section className={styles.card}>
          <div>
            <h2 className={styles.title}>Sign up</h2>
            <p className={styles.subtitle}>Magic link is the fastest way to start. You can switch to password anytime.</p>
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
                  placeholder="12+ characters and a number"
                  required
                />
              </div>
            ) : null}

            <div className={styles.field}>
              <label className={styles.label} htmlFor="firstName">
                First name (optional)
              </label>
              <input
                className={styles.input}
                id="firstName"
                type="text"
                autoComplete="given-name"
                value={firstName}
                onChange={(event) => setFirstName(event.target.value)}
                placeholder="Ada"
              />
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="lastName">
                Last name (optional)
              </label>
              <input
                className={styles.input}
                id="lastName"
                type="text"
                autoComplete="family-name"
                value={lastName}
                onChange={(event) => setLastName(event.target.value)}
                placeholder="Lovelace"
              />
            </div>

            <div className={styles.actions}>
              <button className={`${styles.button} ${styles.buttonPrimary}`} type="submit" disabled={loading}>
                {loading ? "Working..." : mode === "magic" ? "Send access link" : "Create Talven account"}
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

          <button className={`${styles.button} ${styles.buttonGhost}`} onClick={handleGoogle} disabled={loading}>
            <Image className={styles.googleIcon} src="/google-logo.webp" alt="" aria-hidden="true" width={18} height={18} />
            Continue with Google
          </button>

          <div className={styles.links}>
            <span>
              Already have an account? <Link href={signInHref}>Sign in</Link>
            </span>
            <Link href="/">Return to Talven</Link>
          </div>
        </section>
      </div>
    </div>
  );
}

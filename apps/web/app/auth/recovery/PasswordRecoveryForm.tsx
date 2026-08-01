"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { mapAuthError } from "../../lib/authErrors";
import { getPasswordRecoveryErrorMessage, validateRecoveryPassword } from "../../lib/authPolicy";
import { getSupabaseClient } from "../../lib/supabaseClient";
import styles from "../auth.module.css";

type PasswordRecoveryFormProps = {
  errorCode: string | null;
  nextPath: string;
  recoveryReady: boolean;
};

const ERROR_ID = "password-recovery-error";
const PASSWORD_HELP_ID = "password-recovery-help";

export function PasswordRecoveryForm({ errorCode, nextPath, recoveryReady }: PasswordRecoveryFormProps) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [checkingSession, setCheckingSession] = useState(recoveryReady);
  const [sessionReady, setSessionReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(
    getPasswordRecoveryErrorMessage(errorCode) ??
      (recoveryReady ? null : "Open the password reset link from your email to continue.")
  );

  useEffect(() => {
    if (!recoveryReady) {
      setCheckingSession(false);
      return;
    }

    let active = true;
    const verifySession = async () => {
      try {
        const supabase = getSupabaseClient();
        const { data, error: sessionError } = await supabase.auth.getSession();
        if (!active) {
          return;
        }
        if (sessionError || !data.session) {
          setError("This password reset session is invalid or has expired. Request a new link from sign in.");
          setSessionReady(false);
        } else {
          setError(null);
          setSessionReady(true);
        }
      } catch {
        if (active) {
          setError("Unable to verify this password reset session. Request a new link from sign in.");
          setSessionReady(false);
        }
      } finally {
        if (active) {
          setCheckingSession(false);
        }
      }
    };

    void verifySession();
    return () => {
      active = false;
    };
  }, [recoveryReady]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const validationError = validateRecoveryPassword(password, confirmation);
    if (validationError) {
      setError(validationError);
      return;
    }
    if (!sessionReady) {
      setError("This password reset session is invalid or has expired. Request a new link from sign in.");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const supabase = getSupabaseClient();
      const { error: updateError } = await supabase.auth.updateUser({ password });
      if (updateError) {
        setError(mapAuthError(updateError, "Unable to update your password."));
        return;
      }

      await fetch("/auth/recovery/complete", { method: "POST" });
      router.replace(nextPath);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update your password.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className={styles.card} aria-labelledby="password-recovery-title">
      <div>
        <h2 className={styles.title} id="password-recovery-title">
          Set a new password
        </h2>
        <p className={styles.subtitle}>Choose a password you do not use for another service.</p>
      </div>

      {error ? (
        <div className={styles.error} id={ERROR_ID} role="alert">
          {error}
        </div>
      ) : null}

      {checkingSession ? (
        <div className={styles.notice} role="status">
          Verifying your reset link...
        </div>
      ) : null}

      {sessionReady ? (
        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="new-password">
              New password
            </label>
            <input
              aria-describedby={`${PASSWORD_HELP_ID}${error ? ` ${ERROR_ID}` : ""}`}
              aria-invalid={Boolean(error)}
              autoComplete="new-password"
              className={styles.input}
              id="new-password"
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
            <p className={styles.fieldHelp} id={PASSWORD_HELP_ID}>
              Use at least 12 characters and include a number.
            </p>
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="confirm-password">
              Confirm new password
            </label>
            <input
              aria-describedby={error ? ERROR_ID : undefined}
              aria-invalid={Boolean(error)}
              autoComplete="new-password"
              className={styles.input}
              id="confirm-password"
              onChange={(event) => setConfirmation(event.target.value)}
              required
              type="password"
              value={confirmation}
            />
          </div>

          <div className={styles.actions}>
            <button className={`${styles.button} ${styles.buttonPrimary}`} disabled={saving} type="submit">
              {saving ? "Updating password..." : "Update password"}
            </button>
          </div>
        </form>
      ) : null}

      {!checkingSession && !sessionReady ? (
        <div className={styles.links}>
          <Link href="/signin">Request a new reset link</Link>
          <Link href="/">Return to Talven</Link>
        </div>
      ) : null}
    </section>
  );
}

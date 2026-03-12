"use client";

import { useEffect, useState } from "react";

import { AppShellHeader } from "../../components/AppShellHeader";
import { useAppShell } from "../../components/AppShellProvider";
import chrome from "../../components/app-chrome.module.css";
import { getAccountLabel } from "../../lib/accountLabel";
import { getSupabaseClient } from "../../lib/supabaseClient";
import styles from "./account.module.css";

function getStoredFullName(nameSource: { user_metadata?: Record<string, unknown> } | null): string {
  return (
    (nameSource?.user_metadata?.full_name as string | undefined) ??
    (nameSource?.user_metadata?.name as string | undefined) ??
    ""
  );
}

export default function ProfilePage() {
  const { remainingSeconds, signOut, user: shellUser } = useAppShell();
  const [user, setUser] = useState(shellUser);
  const [fullName, setFullName] = useState(() => getStoredFullName(shellUser));
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(() => shellUser === null);
  const [status, setStatus] = useState<string | null>(null);
  const [statusError, setStatusError] = useState(false);

  useEffect(() => {
    setUser(shellUser);
    setFullName(getStoredFullName(shellUser));
    setLoading(shellUser === null);
  }, [shellUser]);

  const handleSave = async () => {
    if (!user || saving) {
      return;
    }

    setSaving(true);
    setStatus(null);
    setStatusError(false);

    try {
      const supabase = getSupabaseClient();
      const normalizedName = fullName.trim();
      const { error } = await supabase.auth.updateUser({
        data: {
          full_name: normalizedName
        }
      });

      if (error) {
        setStatus(error.message);
        setStatusError(true);
        return;
      }

      setUser((previous) => {
        if (!previous) {
          return previous;
        }

        return {
          ...previous,
          user_metadata: {
            ...previous.user_metadata,
            full_name: normalizedName
          }
        };
      });

      setStatus("Account updated.");
      setStatusError(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader active="account" remainingSeconds={remainingSeconds} accountLabel={getAccountLabel(user)} onSignOut={signOut} />

      <main className={chrome.mainFrame}>
        <section className={`${chrome.heroBlock} ${styles.pageColumn}`}>
          <div>
            <p className={chrome.heroEyebrow}>Account</p>
            <h1 className={chrome.heroTitle}>Your account</h1>
            <p className={chrome.heroText}>A minimal identity card for how your workspace appears.</p>
          </div>
        </section>

        <section className={`${styles.pageColumn} ${styles.profileShell}`}>
          <article className={`${chrome.surface} ${styles.profileCard}`}>
            <div className={styles.cardIntro}>
              <h2 className={styles.cardTitle}>Account details</h2>
              <p className={styles.cardText}>Only the essentials that shape how your name appears across Talven.</p>
            </div>

            <div className={styles.fieldGrid}>
              <label className={chrome.fieldStack}>
                <span className={chrome.fieldLabel}>Email</span>
                <div className={chrome.readonlyField}>{user?.email ?? "-"}</div>
              </label>

              <label className={chrome.fieldStack}>
                <span className={chrome.fieldLabel}>Full name</span>
                <input
                  className={chrome.input}
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  placeholder="Your name"
                  disabled={loading}
                />
              </label>
            </div>

            <div className={styles.actionRow}>
              <button className={chrome.primaryButton} type="button" onClick={handleSave} disabled={saving || loading}>
                {saving ? "Saving..." : "Save changes"}
              </button>
            </div>

            {status ? <p className={`${chrome.inlineStatus} ${statusError ? chrome.inlineStatusError : ""}`}>{status}</p> : null}
          </article>
        </section>
      </main>
    </div>
  );
}

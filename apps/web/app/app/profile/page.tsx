"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { User } from "@supabase/supabase-js";

import styles from "../app.module.css";
import { getSupabaseClient } from "../../lib/supabaseClient";

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [fullName, setFullName] = useState("");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    const loadProfile = async () => {
      const supabase = getSupabaseClient();
      const { data } = await supabase.auth.getSession();
      if (!data.session) {
        router.replace("/signin");
        return;
      }

      const currentUser = data.session.user;
      setUser(currentUser);
      const existingName = (currentUser.user_metadata?.full_name as string | undefined) ?? "";
      setFullName(existingName);
    };

    void loadProfile();
  }, [router]);

  const handleSave = async () => {
    if (!user || saving) {
      return;
    }
    setSaving(true);
    setStatus(null);
    try {
      const supabase = getSupabaseClient();
      const { error } = await supabase.auth.updateUser({
        data: {
          full_name: fullName.trim()
        }
      });

      if (error) {
        setStatus(error.message);
      } else {
        setStatus("Profile updated.");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true" />
          Fathom
        </div>
        <div className={styles.headerActions}>
          <Link className={styles.button} href="/app">
            Back to app
          </Link>
        </div>
      </header>

      <main className={styles.main}>
        <section className={styles.card}>
          <div className={styles.sectionHeader}>
            <div>
              <h1 className={styles.cardTitle}>Profile</h1>
              <p className={styles.cardText}>Update your display name and contact details.</p>
            </div>
          </div>

          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>Email</span>
              <div className={styles.fieldValue}>{user?.email ?? "—"}</div>
            </label>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>Full name</span>
              <input
                className={styles.input}
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="Your name"
              />
            </label>
          </div>

          <div className={styles.actionRow}>
            <button className={styles.primaryButton} type="button" onClick={handleSave} disabled={saving}>
              {saving ? "Saving…" : "Save changes"}
            </button>
            <Link className={styles.secondaryButton} href="/app/billing">
              Manage billing
            </Link>
          </div>

          {status ? <p className={styles.status}>{status}</p> : null}
        </section>
      </main>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { BillingAccountResponse, UsageOverviewResponse } from "@fathom/api-client";
import type { User } from "@supabase/supabase-js";
import { createApiClient } from "@fathom/api-client";

import { AppShellHeader } from "../../components/AppShellHeader";
import { formatDuration } from "../../lib/format";
import { getApiErrorMessage } from "../../lib/apiErrors";
import { getSupabaseClient } from "../../lib/supabaseClient";
import styles from "./profile.module.css";

const getAccountLabel = (user: User | null): string | null => {
  if (!user) {
    return null;
  }
  const fullName = (user.user_metadata?.full_name as string | undefined) ?? (user.user_metadata?.name as string | undefined);
  if (fullName && fullName.trim().length > 0) {
    return fullName.trim();
  }
  const email = user.email ?? null;
  if (!email) {
    return null;
  }
  const localPart = email.split("@")[0];
  return localPart || email;
};

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [usage, setUsage] = useState<UsageOverviewResponse | null>(null);
  const [account, setAccount] = useState<BillingAccountResponse | null>(null);
  const [fullName, setFullName] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<string | null>(null);
  const [statusError, setStatusError] = useState(false);

  useEffect(() => {
    const loadProfile = async () => {
      try {
        const supabase = getSupabaseClient();
        const { data } = await supabase.auth.getSession();
        if (!data.session) {
          router.replace("/signin");
          return;
        }

        const currentUser = data.session.user;
        setUser(currentUser);

        const existingName =
          (currentUser.user_metadata?.full_name as string | undefined) ??
          (currentUser.user_metadata?.name as string | undefined) ??
          "";
        setFullName(existingName);

        const api = createApiClient(data.session.access_token);
        const [{ data: usageData, error: usageError }, { data: accountData, error: accountError }] = await Promise.all([
          api.GET("/billing/usage"),
          api.GET("/billing/account")
        ]);

        if (usageError) {
          setStatus(getApiErrorMessage(usageError, "Unable to load usage."));
          setStatusError(true);
        } else {
          setUsage(usageData ?? null);
        }

        if (accountError) {
          setStatus(getApiErrorMessage(accountError, "Unable to load account state."));
          setStatusError(true);
        } else {
          setAccount(accountData ?? null);
        }
      } catch (err) {
        setStatus(err instanceof Error ? err.message : "Something went wrong.");
        setStatusError(true);
      } finally {
        setLoading(false);
      }
    };

    void loadProfile();
  }, [router]);

  const handleSignOut = async () => {
    const supabase = getSupabaseClient();
    await supabase.auth.signOut();
    router.replace("/signin");
  };

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
      setStatus("Profile updated.");
      setStatusError(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={styles.page}>
      <AppShellHeader
        active="profile"
        remainingSeconds={usage?.total_remaining_seconds ?? null}
        accountLabel={getAccountLabel(user)}
        onSignOut={handleSignOut}
      />

      <main className={styles.main}>
        <section className={styles.summaryCard}>
          <div className={styles.summaryHeader}>
            <h1 className={styles.title}>Profile</h1>
            <p className={styles.subtitle}>Manage your account identity and keep billing details current.</p>
          </div>

          <div className={styles.kpiGrid}>
            <article className={styles.kpi}>
              <p className={styles.kpiLabel}>Display name</p>
              <p className={styles.kpiValue}>{getAccountLabel(user) ?? "Not set"}</p>
            </article>
            <article className={styles.kpi}>
              <p className={styles.kpiLabel}>Current plan</p>
              <p className={styles.kpiValue}>{account?.subscription.plan_name ?? usage?.subscription_plan_name ?? "Free"}</p>
            </article>
            <article className={styles.kpi}>
              <p className={styles.kpiLabel}>Credits remaining</p>
              <p className={styles.kpiValue}>{formatDuration(usage?.total_remaining_seconds ?? 0)}</p>
            </article>
          </div>
        </section>

        <section className={styles.formCard}>
          <h2 className={styles.formTitle}>Account details</h2>

          <div className={styles.fieldGrid}>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>Email</span>
              <div className={styles.readonlyField}>{user?.email ?? "-"}</div>
            </label>

            <label className={styles.field}>
              <span className={styles.fieldLabel}>Full name</span>
              <input
                className={styles.input}
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="Your name"
                disabled={loading}
              />
            </label>
          </div>

          <div className={styles.actionRow}>
            <button className={styles.primaryButton} type="button" onClick={handleSave} disabled={saving || loading}>
              {saving ? "Saving..." : "Save changes"}
            </button>
            <Link className={styles.secondaryButton} href="/app/billing">
              Open billing
            </Link>
          </div>

          {status ? (
            <p className={`${styles.status} ${statusError ? styles.statusError : styles.statusSuccess}`}>{status}</p>
          ) : null}
        </section>
      </main>
    </div>
  );
}

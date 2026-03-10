"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { BillingAccountResponse, UsageOverviewResponse } from "@fathom/api-client";
import type { User } from "@supabase/supabase-js";
import { createApiClient } from "@fathom/api-client";

import { AppShellHeader } from "../../components/AppShellHeader";
import chrome from "../../components/app-chrome.module.css";
import { formatDuration } from "../../lib/format";
import { getApiErrorMessage } from "../../lib/apiErrors";
import { getAccountLabel } from "../../lib/accountLabel";
import { getSupabaseClient } from "../../lib/supabaseClient";
import styles from "./profile.module.css";

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
    <div className={chrome.pageFrame}>
      <AppShellHeader
        active="profile"
        remainingSeconds={usage?.total_remaining_seconds ?? null}
        accountLabel={getAccountLabel(user)}
        onSignOut={handleSignOut}
      />

      <main className={chrome.mainFrame}>
        <section className={chrome.heroBlock}>
          <div>
            <p className={chrome.heroEyebrow}>Profile</p>
            <h1 className={chrome.heroTitle}>Account identity</h1>
            <p className={chrome.heroText}>Keep your Talven identity current and make sure billing context stays easy to read.</p>
          </div>
        </section>

        <section className={chrome.heroSplit}>
          <article className={chrome.surfaceStrong}>
            <div className={chrome.surfaceHeader}>
              <div>
                <h2 className={chrome.surfaceTitle}>Account details</h2>
                <p className={chrome.surfaceText}>Update the name attached to your workspace.</p>
              </div>
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

            <div className={chrome.actionRow}>
              <button className={chrome.primaryButton} type="button" onClick={handleSave} disabled={saving || loading}>
                {saving ? "Saving..." : "Save changes"}
              </button>
              <Link className={chrome.secondaryButton} href="/app/billing">
                Open billing
              </Link>
            </div>

            {status ? (
              <p className={`${chrome.inlineStatus} ${statusError ? chrome.inlineStatusError : ""}`}>{status}</p>
            ) : null}
          </article>

          <aside className={chrome.surface}>
            <div className={chrome.surfaceHeader}>
              <div>
                <h2 className={chrome.surfaceTitle}>Current posture</h2>
                <p className={chrome.surfaceText}>A concise read on who this account is and what access it carries.</p>
              </div>
            </div>

            <div className={chrome.metricGrid}>
              <article className={chrome.metricCard}>
                <p className={chrome.metricLabel}>Display name</p>
                <p className={chrome.metricValue}>{getAccountLabel(user) ?? "Not set"}</p>
              </article>
              <article className={chrome.metricCard}>
                <p className={chrome.metricLabel}>Current plan</p>
                <p className={chrome.metricValue}>{account?.subscription.plan_name ?? usage?.subscription_plan_name ?? "Free"}</p>
              </article>
              <article className={chrome.metricCard}>
                <p className={chrome.metricLabel}>Credits remaining</p>
                <p className={chrome.metricValue}>{formatDuration(usage?.total_remaining_seconds ?? 0)}</p>
              </article>
            </div>
          </aside>
        </section>
      </main>
    </div>
  );
}

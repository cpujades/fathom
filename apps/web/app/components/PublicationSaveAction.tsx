"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { createApiClient, type PublicationLibraryEntryResponse } from "@fathom/api-client";
import type { Session } from "@supabase/supabase-js";

import { invalidateBriefingsCache } from "../lib/appDataCache";
import { getApiErrorMessage } from "../lib/apiErrors";
import { getSupabaseClient } from "../lib/supabaseClient";
import { buildSignInPath } from "../lib/url";
import styles from "./publication-save-action.module.css";

type PublicationSaveActionProps = {
  publicPath: string;
  publicSlug: string;
};

export function PublicationSaveAction({
  publicPath,
  publicSlug
}: PublicationSaveActionProps) {
  const [session, setSession] = useState<Session | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [entry, setEntry] = useState<PublicationLibraryEntryResponse | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const authRevision = useRef(0);

  const loadEntry = useCallback(async (activeSession: Session) => {
    const api = createApiClient(activeSession.access_token);
    const { data, error: apiError } = await api.GET("/publications/{public_slug}/library-entry", {
      params: { path: { public_slug: publicSlug } }
    });
    if (apiError) {
      throw apiError;
    }
    return data ?? null;
  }, [publicSlug]);

  useEffect(() => {
    let active = true;
    let receivedAuthEvent = false;
    const supabase = getSupabaseClient();

    const applySession = async (nextSession: Session | null) => {
      if (!active) return;
      const revision = ++authRevision.current;
      setSession(nextSession);
      setEntry(null);
      setError(null);
      setSaving(false);
      setAuthLoading(Boolean(nextSession));
      if (nextSession) {
        try {
          const nextEntry = await loadEntry(nextSession);
          if (active && authRevision.current === revision) setEntry(nextEntry);
        } catch (loadError) {
          if (active && authRevision.current === revision) {
            setError(getApiErrorMessage(loadError, "Unable to check your library."));
          }
        }
      }
      if (active && authRevision.current === revision) setAuthLoading(false);
    };

    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      receivedAuthEvent = true;
      void applySession(nextSession);
    });
    void supabase.auth.getSession()
      .then(({ data }) => {
        if (active && !receivedAuthEvent) void applySession(data.session);
      })
      .catch(() => {
        if (active && !receivedAuthEvent) {
          setError("Unable to check your account.");
          setAuthLoading(false);
        }
      });

    return () => {
      active = false;
      authRevision.current += 1;
      listener.subscription.unsubscribe();
    };
  }, [loadEntry]);

  const save = async () => {
    if (!session || saving) return;
    const revision = authRevision.current;
    setSaving(true);
    setError(null);
    try {
      const api = createApiClient(session.access_token);
      const { data, error: apiError } = await api.POST("/publications/{public_slug}/save", {
        params: { path: { public_slug: publicSlug } }
      });
      if (apiError) throw apiError;
      if (authRevision.current !== revision) return;
      setEntry(data ?? null);
      invalidateBriefingsCache(session.user.id);
    } catch (saveError) {
      if (authRevision.current !== revision) return;
      setError(getApiErrorMessage(saveError, "Unable to save this briefing."));
    } finally {
      if (authRevision.current === revision) setSaving(false);
    }
  };

  const className = styles.primaryAction;
  const content = (() => {
    if (authLoading) return <button className={className} type="button" disabled>Checking library…</button>;
    if (!session) return <Link className={className} href={buildSignInPath(publicPath)}>Sign in to save</Link>;
    if (entry?.session_path && entry.state === "saved") {
      return <Link className={className} href={entry.session_path}>View in library</Link>;
    }
    if (entry?.session_path && entry.state === "processing") {
      return <Link className={className} href={entry.session_path}>Open current briefing</Link>;
    }
    return (
      <button className={className} type="button" onClick={() => void save()} disabled={saving}>
        {saving ? "Saving…" : "Save to library"}
      </button>
    );
  })();

  return (
    <div className={styles.container}>
      {content}
      {entry?.state === "saved" ? <p role="status">Saved without using video time.</p> : null}
      {error ? <p className={styles.error} role="alert">{error}</p> : null}
    </div>
  );
}

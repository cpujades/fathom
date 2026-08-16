"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { createApiClient, type ExploreBriefingItem, type PublicationLibraryEntryResponse } from "@fathom/api-client";
import type { Session } from "@supabase/supabase-js";

import { invalidateBriefingsCache } from "../lib/appDataCache";
import { getApiErrorMessage } from "../lib/apiErrors";
import { formatExactDuration, formatExploreTopic } from "../lib/format";
import { getSupabaseClient } from "../lib/supabaseClient";
import { buildSignInPath } from "../lib/url";
import styles from "./explore.module.css";

export function ExploreGrid({ items }: { items: ExploreBriefingItem[] }) {
  const [session, setSession] = useState<Session | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [savingSlug, setSavingSlug] = useState<string | null>(null);
  const [entries, setEntries] = useState<Record<string, PublicationLibraryEntryResponse>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const authRevision = useRef(0);

  useEffect(() => {
    let active = true;
    let receivedAuthEvent = false;
    const supabase = getSupabaseClient();

    const applySession = (nextSession: Session | null) => {
      const revision = ++authRevision.current;
      setSession(nextSession);
      setEntries({});
      setErrors({});
      setLoadError(null);
      setSavingSlug(null);
      setAuthLoading(Boolean(nextSession));

      if (!nextSession) return;

      const api = createApiClient(nextSession.access_token);
      void api.POST("/publications/library-entries", {
        body: { public_slugs: items.map((item) => item.public_slug) }
      }).then(({ data, error }) => {
        if (!active || authRevision.current !== revision) return;
        if (error || !data) throw error ?? new Error("Empty library state response.");
        setEntries(data.entries);
      }).catch((error) => {
        if (!active || authRevision.current !== revision) return;
        setLoadError(getApiErrorMessage(error, "Unable to check your library."));
      }).finally(() => {
        if (active && authRevision.current === revision) setAuthLoading(false);
      });
    };

    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (!active) return;
      receivedAuthEvent = true;
      applySession(nextSession);
    });
    void supabase.auth.getSession()
      .then(({ data }) => {
        if (active && !receivedAuthEvent) applySession(data.session);
      })
      .catch(() => {
        if (!active || receivedAuthEvent) return;
        setLoadError("Unable to check your account.");
        setAuthLoading(false);
      });

    return () => {
      active = false;
      authRevision.current += 1;
      listener.subscription.unsubscribe();
    };
  }, [items]);

  const save = async (item: ExploreBriefingItem) => {
    if (!session || savingSlug) return;
    const revision = authRevision.current;
    setSavingSlug(item.public_slug);
    setErrors((current) => ({ ...current, [item.public_slug]: "" }));
    try {
      const api = createApiClient(session.access_token);
      const { data, error } = await api.POST("/publications/{public_slug}/save", {
        params: { path: { public_slug: item.public_slug } }
      });
      if (error || !data) throw error ?? new Error("Empty save response.");
      if (authRevision.current !== revision) return;
      setEntries((current) => ({ ...current, [item.public_slug]: data }));
      invalidateBriefingsCache(session.user.id);
    } catch (saveError) {
      if (authRevision.current !== revision) return;
      setErrors((current) => ({
        ...current,
        [item.public_slug]: getApiErrorMessage(saveError, "Unable to save this briefing.")
      }));
    } finally {
      if (authRevision.current === revision) setSavingSlug(null);
    }
  };

  return (
    <section className={styles.grid} aria-label="Curated briefings">
      {loadError ? <p className={styles.loadError} role="alert">{loadError}</p> : null}
      {items.map((item) => {
        const entry = entries[item.public_slug];
        return (
          <article className={styles.card} key={item.public_slug}>
            <Link className={styles.mediaLink} href={item.public_path} aria-label={`Read ${item.title}`}>
              <span className={styles.mediaFrame}>
                {item.source_thumbnail_url ? (
                  <Image
                    className={styles.thumbnail}
                    src={item.source_thumbnail_url}
                    alt=""
                    fill
                    sizes="(max-width: 760px) 92vw, 360px"
                  />
                ) : <span className={styles.mediaFallback}>Talven briefing</span>}
              </span>
            </Link>
            <div className={styles.cardBody}>
              <div className={styles.cardMeta}>
                <Link href={`/explore?topic=${encodeURIComponent(item.topic)}`}>{formatExploreTopic(item.topic)}</Link>
                {item.source_duration_seconds ? <span>{formatExactDuration(item.source_duration_seconds)}</span> : null}
              </div>
              <h2><Link href={item.public_path}>{item.title}</Link></h2>
              {item.author ? <p>By {item.author}</p> : null}
              <div className={styles.cardActions}>
                <Link href={item.public_path}>Read briefing</Link>
                {entry?.session_path ? (
                  <Link className={styles.saveAction} href={entry.session_path}>View in library</Link>
                ) : !authLoading && !session ? (
                  <Link className={styles.saveAction} href={buildSignInPath(item.public_path)}>Sign in to save</Link>
                ) : (
                  <button
                    className={styles.saveAction}
                    type="button"
                    onClick={() => void save(item)}
                    disabled={authLoading || savingSlug !== null}
                  >
                    {savingSlug === item.public_slug ? "Saving…" : "Save to library"}
                  </button>
                )}
              </div>
              {errors[item.public_slug] ? <p className={styles.cardError} role="alert">{errors[item.public_slug]}</p> : null}
            </div>
          </article>
        );
      })}
    </section>
  );
}

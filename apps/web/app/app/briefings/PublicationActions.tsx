"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { createApiClient, type PublicationStateResponse } from "@fathom/api-client";

import { getApiErrorMessage } from "../../lib/apiErrors";
import { formatExploreTopic } from "../../lib/format";
import styles from "./publication-actions.module.css";

type PublicationActionsProps = {
  accessToken: string;
  sessionId: string;
  title: string;
};

export function PublicationActions({ accessToken, sessionId, title }: PublicationActionsProps) {
  const [publication, setPublication] = useState<PublicationStateResponse | null>(null);
  const [topic, setTopic] = useState<PublicationStateResponse["available_topics"][number] | "">("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const requestRevision = useRef(0);

  useEffect(() => {
    let active = true;
    const revision = ++requestRevision.current;
    setLoading(true);
    setPublication(null);
    setSaving(false);
    setError(null);
    setNotice(null);

    void (async () => {
      try {
        const api = createApiClient(accessToken);
        const { data, error: apiError } = await api.GET("/briefing-sessions/{session_id}/publication", {
          params: { path: { session_id: sessionId } }
        });
        if (apiError || !data) throw apiError ?? new Error("Empty publication response.");
        if (!active || requestRevision.current !== revision) return;
        setPublication(data);
        setTopic(data.topic ?? "");
      } catch (loadError) {
        if (!active || requestRevision.current !== revision) return;
        setError(getApiErrorMessage(loadError, "Unable to load sharing controls."));
      } finally {
        if (active && requestRevision.current === revision) setLoading(false);
      }
    })();

    return () => {
      active = false;
      if (requestRevision.current === revision) requestRevision.current += 1;
    };
  }, [accessToken, sessionId]);

  const update = async (visibility: "private" | "unlisted" | "listed") => {
    if (saving) return;
    const revision = requestRevision.current;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const api = createApiClient(accessToken);
      const { data, error: apiError } = await api.POST("/briefing-sessions/{session_id}/publication", {
        params: { path: { session_id: sessionId } },
        body: { visibility, topic: visibility === "listed" ? topic || null : null }
      });
      if (apiError || !data) throw apiError ?? new Error("Empty publication response.");
      if (requestRevision.current !== revision) return;
      setPublication(data);
      setTopic(data.topic ?? "");
      setNotice(
        visibility === "private"
          ? "Public access removed."
          : visibility === "listed"
            ? "Added to Explore."
            : "Private sharing link ready."
      );
    } catch (updateError) {
      if (requestRevision.current !== revision) return;
      setError(getApiErrorMessage(updateError, "Unable to update sharing."));
    } finally {
      if (requestRevision.current === revision) setSaving(false);
    }
  };

  const publicUrl = publication?.public_path && typeof window !== "undefined"
    ? new URL(publication.public_path, window.location.origin).toString()
    : null;

  const copyLink = async () => {
    if (!publicUrl) return;
    setError(null);
    setNotice(null);
    try {
      await window.navigator.clipboard.writeText(publicUrl);
      setNotice("Public link copied.");
    } catch {
      setError("Could not copy the link. Open the public page and copy its address instead.");
    }
  };

  const shareLink = async () => {
    if (!publicUrl || !("share" in window.navigator)) return;
    try {
      await window.navigator.share({ title, url: publicUrl });
    } catch (shareError) {
      if (shareError instanceof DOMException && shareError.name === "AbortError") return;
      setError("Could not open the device share menu. Copy the link instead.");
    }
  };

  if (loading) {
    return <section className={styles.card} aria-label="Sharing"><p>Loading sharing controls…</p></section>;
  }
  if (!publication) {
    return <section className={styles.card} aria-label="Sharing"><p className={styles.error} role="alert">{error}</p></section>;
  }

  const isPublic = publication.visibility !== "private";
  const canUseNativeShare = typeof window !== "undefined" && "share" in window.navigator;
  return (
    <section className={styles.card} aria-labelledby="sharing-heading">
      <div className={styles.heading}>
        <div>
          <p className={styles.kicker}>Sharing</p>
          <h2 id="sharing-heading">{isPublic ? "This briefing has a public link" : "Share this briefing with a link"}</h2>
        </div>
        <span>{publication.visibility === "listed" ? "In Explore" : isPublic ? "Unlisted" : "Private"}</span>
      </div>

      {isPublic && publication.public_path ? (
        <div className={styles.actions}>
          <Link className={styles.primaryAction} href={publication.public_path}>View public page</Link>
          <button type="button" onClick={() => void copyLink()}>Copy link</button>
          {canUseNativeShare ? (
            <button type="button" onClick={() => void shareLink()}>Share…</button>
          ) : null}
          {publication.visibility === "listed" ? (
            <button type="button" onClick={() => void update("unlisted")} disabled={saving}>Remove from Explore</button>
          ) : null}
          <button className={styles.dangerAction} type="button" onClick={() => void update("private")} disabled={saving}>
            {saving ? "Updating…" : "Remove public access"}
          </button>
        </div>
      ) : (
        <div className={styles.actions}>
          <button className={styles.primaryAction} type="button" onClick={() => void update("unlisted")} disabled={saving}>
            {saving ? "Creating link…" : "Create sharing link"}
          </button>
          <p>Anyone with the link can read it. It will not appear in Explore.</p>
        </div>
      )}

      {publication.can_list && publication.visibility !== "listed" ? (
        <form
          className={styles.exploreForm}
          onSubmit={(event) => {
            event.preventDefault();
            void update("listed");
          }}
        >
          <label>
            <span>Explore topic</span>
            <select
              value={topic}
              onChange={(event) => {
                const selected = publication.available_topics.find((value) => value === event.target.value);
                setTopic(selected ?? "");
              }}
              required
            >
              <option value="" disabled>Select a topic</option>
              {publication.available_topics.map((value) => (
                <option value={value} key={value}>{formatExploreTopic(value)}</option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={saving || !topic}>{saving ? "Updating…" : "Add to Explore"}</button>
        </form>
      ) : null}

      {notice ? <p className={styles.notice} role="status">{notice}</p> : null}
      {error ? <p className={styles.error} role="alert">{error}</p> : null}
    </section>
  );
}

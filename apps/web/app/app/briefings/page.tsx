"use client";

import Image from "next/image";
import Link from "next/link";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { createApiClient } from "@fathom/api-client";

import { AppShellHeader } from "../../components/AppShellHeader";
import { useAppShell } from "../../components/AppShellProvider";
import chrome from "../../components/app-chrome.module.css";
import shellStyles from "../app.module.css";
import styles from "./briefings.module.css";
import { getAccountLabel } from "../../lib/accountLabel";
import { getApiErrorMessage } from "../../lib/apiErrors";
import type {
  BriefingListItem,
  BriefingListResponse,
  BriefingListSort
} from "../../lib/briefings";
import { DEFAULT_BRIEFINGS_LIMIT } from "../../lib/briefings";
import { formatDateTime, formatDuration, formatExactDuration } from "../../lib/format";
import {
  getCachedBriefings,
  hasFreshBriefingsCache,
  invalidateBriefingsCache,
  loadBriefings,
  prefetchSessionSnapshot
} from "../../lib/appDataCache";

const EMPTY_BRIEFINGS_RESPONSE: BriefingListResponse = {
  items: [],
  total_count: 0,
  limit: DEFAULT_BRIEFINGS_LIMIT,
  offset: 0,
  has_more: false,
  query: null,
  sort: "newest",
  source_type: "all"
};

const SORT_OPTIONS: Array<{ value: BriefingListSort; label: string }> = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" }
];

function formatBriefingCount(count: number): string {
  return `${count} ${count === 1 ? "briefing" : "briefings"}`;
}

function getSessionIdFromPath(path: string | null | undefined): string | null {
  if (!path) {
    return null;
  }

  const match = path.match(/\/app\/briefings\/sessions\/([^/?#]+)/);
  return match?.[1] ?? null;
}

function getSourceTypeLabel(sourceType: BriefingListItem["source_type"]): string {
  if (sourceType === "youtube") {
    return "YouTube";
  }
  if (sourceType === "url") {
    return "Web";
  }
  return "Source";
}

function getStatusLabel(loading: boolean, shellLoading: boolean, totalCount: number): string {
  if (loading || shellLoading) {
    return "Syncing library";
  }

  return formatBriefingCount(totalCount);
}

export default function BriefingsPage() {
  const cachedBriefings = getCachedBriefings();
  const { accessToken, loading: shellLoading, remainingSeconds, signOut, user } = useAppShell();

  const [briefings, setBriefings] = useState<BriefingListResponse>(cachedBriefings ?? EMPTY_BRIEFINGS_RESPONSE);
  const [loading, setLoading] = useState(() => cachedBriefings === null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState(cachedBriefings?.query ?? "");
  const [sort, setSort] = useState<BriefingListSort>(cachedBriefings?.sort ?? "newest");
  const [confirmDeleteSessionId, setConfirmDeleteSessionId] = useState<string | null>(null);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);

  const deferredSearch = useDeferredValue(searchInput.trim());

  useEffect(() => {
    if (!accessToken) {
      return;
    }

    let active = true;
    const usingDefaultQuery = !deferredSearch && sort === "newest";
    if (usingDefaultQuery && hasFreshBriefingsCache()) {
      const nextCachedBriefings = getCachedBriefings();
      if (nextCachedBriefings) {
        setBriefings(nextCachedBriefings);
        setLoading(false);
        setError(null);
      }
      return;
    }

    setLoading(true);
    setConfirmDeleteSessionId(null);

    const syncBriefings = async () => {
      try {
        const response = await loadBriefings(accessToken, {
          limit: DEFAULT_BRIEFINGS_LIMIT,
          offset: 0,
          query: deferredSearch,
          sort
        });

        if (active) {
          setBriefings(response);
          setError(null);
        }
      } catch (err) {
        if (active) {
          setError(getApiErrorMessage(err, "Unable to load your briefing library."));
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void syncBriefings();

    return () => {
      active = false;
    };
  }, [accessToken, deferredSearch, sort]);

  const hasFilters = deferredSearch.length > 0 || sort !== "newest";
  const helperText = useMemo(() => {
    if (briefings.total_count === 0 && hasFilters) {
      return "No briefings match the current filters.";
    }
    if (briefings.total_count === 0) {
      return "No briefings yet. Start your first one from the workspace.";
    }
    if (briefings.total_count > briefings.items.length) {
      return `Showing ${briefings.items.length} of ${briefings.total_count} briefings.`;
    }
    return `${formatBriefingCount(briefings.total_count)} in your library.`;
  }, [briefings.items.length, briefings.total_count, hasFilters]);

  const prefetchBriefing = (entry: BriefingListItem) => {
    const sessionId = getSessionIdFromPath(entry.session_path);
    if (!accessToken || !sessionId) {
      return;
    }

    void prefetchSessionSnapshot(accessToken, sessionId);
  };

  const handleLoadMore = async () => {
    if (!accessToken || loadingMore || !briefings.has_more) {
      return;
    }

    setLoadingMore(true);
    try {
      const response = await loadBriefings(accessToken, {
        limit: DEFAULT_BRIEFINGS_LIMIT,
        offset: briefings.items.length,
        query: deferredSearch,
        sort
      });

      setBriefings((current) => ({
        ...response,
        items: [...current.items, ...response.items],
        offset: 0
      }));
      setError(null);
    } catch (err) {
      setError(getApiErrorMessage(err, "Unable to load more briefings."));
    } finally {
      setLoadingMore(false);
    }
  };

  const handleDeleteBriefing = async (entry: BriefingListItem) => {
    if (!accessToken || deletingSessionId) {
      return;
    }

    setDeletingSessionId(entry.session_id);
    try {
      const api = createApiClient(accessToken);
      const { error: deleteError } = await api.DELETE("/briefing-sessions/{session_id}", {
        params: {
          path: {
            session_id: entry.session_id
          }
        }
      });

      if (deleteError) {
        throw deleteError;
      }

      invalidateBriefingsCache();
      setBriefings((current) => {
        const nextItems = current.items.filter((item) => item.session_id !== entry.session_id);
        const nextTotalCount = Math.max(current.total_count - 1, 0);

        return {
          ...current,
          items: nextItems,
          total_count: nextTotalCount,
          has_more: nextItems.length < nextTotalCount
        };
      });
      setConfirmDeleteSessionId(null);
      setError(null);
    } catch (err) {
      setError(getApiErrorMessage(err, "Unable to remove this briefing from history."));
    } finally {
      setDeletingSessionId(null);
    }
  };

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader
        active="briefings"
        remainingSeconds={remainingSeconds}
        accountLabel={getAccountLabel(user)}
        onSignOut={signOut}
      />

      <main className={chrome.mainFrame}>
        <section className={`${chrome.heroBlock} ${shellStyles.pageColumn}`}>
          <div>
            <p className={chrome.heroEyebrow}>Briefings</p>
            <h1 className={chrome.heroTitle}>Your briefing library</h1>
            <p className={chrome.heroText}>
              Search, revisit, and trim past briefings without losing the thread back to the original source.
            </p>
          </div>
          <div className={chrome.heroMeta}>
            <span className={chrome.statusPillMuted}>Available {formatDuration(remainingSeconds ?? 0)}</span>
            <span className={chrome.statusPillMuted}>
              {getStatusLabel(loading, shellLoading, briefings.total_count)}
            </span>
          </div>
        </section>

        <section className={`${chrome.surface} ${shellStyles.pageColumn} ${styles.librarySurface}`}>
          <div className={chrome.surfaceHeader}>
            <div>
              <h2 className={chrome.surfaceTitle}>Library</h2>
              <p className={chrome.surfaceText}>{helperText}</p>
            </div>
          </div>

          <div className={styles.controlsGrid}>
            <label className={chrome.fieldStack}>
              <span className={chrome.fieldLabel}>Search</span>
              <input
                className={chrome.input}
                type="search"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Search by title, author, or source"
              />
            </label>

            <label className={chrome.fieldStack}>
              <span className={chrome.fieldLabel}>Sort</span>
              <select
                className={styles.select}
                value={sort}
                onChange={(event) => setSort(event.target.value as BriefingListSort)}
              >
                {SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {loading && briefings.items.length === 0 ? (
            <p className={chrome.emptyState}>Loading your briefing library…</p>
          ) : briefings.items.length === 0 ? (
            <p className={chrome.emptyState}>{helperText}</p>
          ) : (
            <div className={styles.libraryList}>
              {briefings.items.map((entry) => {
                const confirmingDelete = confirmDeleteSessionId === entry.session_id;
                const deletingThisEntry = deletingSessionId === entry.session_id;

                return (
                  <article className={styles.libraryRow} key={entry.session_id}>
                    <div className={styles.libraryRowBody}>
                      <div className={styles.libraryRowMain}>
                        <div className={styles.libraryMedia}>
                          <div className={styles.libraryThumbnailFrame}>
                            {entry.source_thumbnail_url ? (
                              <Image
                                className={styles.libraryThumbnail}
                                src={entry.source_thumbnail_url}
                                alt=""
                                fill
                                sizes="72px"
                              />
                            ) : (
                              <div className={styles.libraryThumbnailFallback}>
                                <span>{getSourceTypeLabel(entry.source_type)}</span>
                              </div>
                            )}
                          </div>
                        </div>

                        <div className={styles.libraryRowContent}>
                          <div className={styles.libraryRowHeader}>
                            <div className={styles.libraryTitleBlock}>
                              <div className={styles.titleRow}>
                                <Link
                                  className={styles.libraryTitleLink}
                                  href={entry.session_path}
                                  onMouseEnter={() => prefetchBriefing(entry)}
                                  onFocus={() => prefetchBriefing(entry)}
                                >
                                  {entry.title}
                                </Link>
                                <span className={chrome.statusPillMuted}>{getSourceTypeLabel(entry.source_type)}</span>
                              </div>

                              <div className={styles.metaRow}>
                                <span>{formatDateTime(entry.created_at)}</span>
                                {entry.author ? <span>By {entry.author}</span> : null}
                                {entry.source_duration_seconds ? <span>{formatExactDuration(entry.source_duration_seconds)}</span> : null}
                              </div>
                            </div>

                            <div className={styles.rowActions}>
                              <div className={styles.actionSet}>
                                <Link
                                  className={chrome.secondaryButton}
                                  href={entry.session_path}
                                  onMouseEnter={() => prefetchBriefing(entry)}
                                  onFocus={() => prefetchBriefing(entry)}
                                >
                                  Open briefing
                                </Link>
                                <a
                                  className={chrome.ghostButton}
                                  href={entry.source_url}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  Open source
                                </a>
                                {!confirmingDelete ? (
                                  <button
                                    className={styles.menuDangerAction}
                                    type="button"
                                    onClick={() => setConfirmDeleteSessionId(entry.session_id)}
                                  >
                                    Remove
                                  </button>
                                ) : null}
                              </div>

                              {confirmingDelete ? (
                                <div className={styles.confirmBlock}>
                                  <p className={styles.confirmText}>Remove this briefing from history?</p>
                                  <div className={styles.confirmActions}>
                                    <button
                                      className={chrome.ghostButton}
                                      type="button"
                                      onClick={() => setConfirmDeleteSessionId(null)}
                                    >
                                      Keep briefing
                                    </button>
                                    <button
                                      className={styles.dangerButton}
                                      type="button"
                                      onClick={() => void handleDeleteBriefing(entry)}
                                      disabled={deletingThisEntry}
                                    >
                                      {deletingThisEntry ? "Removing…" : "Remove from history"}
                                    </button>
                                  </div>
                                </div>
                              ) : null}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}

          {briefings.has_more ? (
            <div className={styles.loadMoreRow}>
              <button
                className={chrome.secondaryButton}
                type="button"
                onClick={() => void handleLoadMore()}
                disabled={loadingMore}
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            </div>
          ) : null}

          {error ? <p className={`${chrome.inlineStatus} ${chrome.inlineStatusError}`}>{error}</p> : null}
        </section>
      </main>
    </div>
  );
}

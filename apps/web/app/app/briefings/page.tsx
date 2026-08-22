"use client";

import { type MouseEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createApiClient } from "@fathom/api-client";

import { AppShellHeader } from "../../components/AppShellHeader";
import { useAppShell } from "../../components/AppShellProvider";
import chrome from "../../components/app-chrome";
import shellStyles from "../app.module.css";
import styles from "./briefings-page.module.css";
import { getAccountLabel } from "../../lib/accountLabel";
import { getApiErrorMessage } from "../../lib/apiErrors";
import type {
  BriefingListItem,
  BriefingListResponse,
  BriefingListSort
} from "../../lib/briefings";
import { DEFAULT_BRIEFINGS_LIMIT } from "../../lib/briefings";
import {
  getCachedBriefings,
  hasFreshBriefingsCache,
  invalidateBriefingsCache,
  isAuthenticatedDataScopeChangedError,
  loadBriefings,
  prefetchSessionSnapshot
} from "../../lib/appDataCache";
import { BriefingLibraryRow, isBriefingProcessing } from "./BriefingLibraryRow";

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
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" }
];
const LIBRARY_SEARCH_DEBOUNCE_MS = 300;

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

function getStatusLabel(loading: boolean, shellLoading: boolean, totalCount: number, activeCount: number): string {
  if (loading || shellLoading) {
    return "Syncing library";
  }
  if (activeCount > 0) {
    return `${activeCount} in progress`;
  }

  return formatBriefingCount(totalCount);
}

export default function BriefingsPage() {
  const router = useRouter();
  const { accessToken, loading: shellLoading, remainingSeconds, signOut, user } = useAppShell();
  const userId = user?.id ?? null;
  const cachedBriefings = userId ? getCachedBriefings(userId) : null;

  const [briefings, setBriefings] = useState<BriefingListResponse>(cachedBriefings ?? EMPTY_BRIEFINGS_RESPONSE);
  const [loading, setLoading] = useState(() => cachedBriefings === null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState(cachedBriefings?.query ?? "");
  const [sort, setSort] = useState<BriefingListSort>(cachedBriefings?.sort ?? "newest");
  const [confirmDeleteSessionId, setConfirmDeleteSessionId] = useState<string | null>(null);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [openingSessionId, setOpeningSessionId] = useState<string | null>(null);
  const [libraryNotice, setLibraryNotice] = useState<string | null>(null);
  const libraryNoticeRef = useRef<HTMLParagraphElement | null>(null);
  const removeButtonRefs = useRef(new Map<string, HTMLButtonElement>());

  const normalizedSearch = searchInput.trim();
  const [debouncedSearch, setDebouncedSearch] = useState(normalizedSearch);
  const activeBriefingCount = useMemo(
    () => briefings.items.filter((entry) => isBriefingProcessing(entry)).length,
    [briefings.items]
  );

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setDebouncedSearch(normalizedSearch);
    }, LIBRARY_SEARCH_DEBOUNCE_MS);

    return () => window.clearTimeout(timeoutId);
  }, [normalizedSearch]);

  useEffect(() => {
    if (!accessToken || !userId) {
      return;
    }

    let active = true;
    const usingDefaultQuery = !debouncedSearch && sort === "newest";
    if (usingDefaultQuery && hasFreshBriefingsCache(userId)) {
      const nextCachedBriefings = getCachedBriefings(userId);
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
        const response = await loadBriefings(userId, accessToken, {
          limit: DEFAULT_BRIEFINGS_LIMIT,
          offset: 0,
          query: debouncedSearch,
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
  }, [accessToken, debouncedSearch, sort, userId]);

  useEffect(() => {
    if (!accessToken || !userId || activeBriefingCount === 0) {
      return;
    }

    let active = true;
    let refreshing = false;
    const intervalId = window.setInterval(() => {
      if (refreshing) {
        return;
      }

      refreshing = true;
      void loadBriefings(userId, accessToken, {
        limit: Math.max(DEFAULT_BRIEFINGS_LIMIT, briefings.items.length),
        offset: 0,
        query: debouncedSearch,
        sort
      })
        .then((response) => {
          if (active) {
            setBriefings(response);
            setError(null);
          }
        })
        .catch(() => {
          // Keep the current library visible if a background refresh misses.
        })
        .finally(() => {
          refreshing = false;
        });
    }, 8000);

    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [accessToken, activeBriefingCount, briefings.items.length, debouncedSearch, sort, userId]);

  const hasFilters = debouncedSearch.length > 0 || sort !== "newest";
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
  const showLibraryHelper = loading || briefings.items.length > 0 || hasFilters;

  const prefetchBriefing = (entry: BriefingListItem) => {
    const sessionId = getSessionIdFromPath(entry.session_path);
    if (!accessToken || !userId || !sessionId) {
      return;
    }

    void prefetchSessionSnapshot(userId, accessToken, sessionId);
  };

  const openBriefing = async (event: MouseEvent<HTMLAnchorElement>, entry: BriefingListItem) => {
    if (!accessToken || !userId || openingSessionId) {
      return;
    }

    const sessionId = getSessionIdFromPath(entry.session_path);
    if (!sessionId) {
      return;
    }

    event.preventDefault();
    setOpeningSessionId(entry.session_id);
    try {
      await prefetchSessionSnapshot(userId, accessToken, sessionId);
    } catch (error) {
      if (isAuthenticatedDataScopeChangedError(error)) {
        return;
      }
      // Navigation should still work if the warm prefetch misses.
    }
    router.push(entry.session_path);
  };

  const handleLoadMore = async () => {
    if (!accessToken || !userId || loadingMore || !briefings.has_more) {
      return;
    }

    setLoadingMore(true);
    try {
      const response = await loadBriefings(userId, accessToken, {
        limit: DEFAULT_BRIEFINGS_LIMIT,
        offset: briefings.items.length,
        query: debouncedSearch,
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
    if (!accessToken || !userId || deletingSessionId) {
      return;
    }

    setDeletingSessionId(entry.session_id);
    setLibraryNotice(null);
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

      invalidateBriefingsCache(userId);
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
      setLibraryNotice("Briefing archived. Submitting the same source restores it.");
      window.requestAnimationFrame(() => libraryNoticeRef.current?.focus());
    } catch (err) {
      setError(getApiErrorMessage(err, "Unable to archive this briefing."));
    } finally {
      setDeletingSessionId(null);
    }
  };

  const closeDeleteConfirmation = (sessionId: string) => {
    setConfirmDeleteSessionId(null);
    window.requestAnimationFrame(() => removeButtonRefs.current.get(sessionId)?.focus());
  };

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader
        active="briefings"
        remainingSeconds={remainingSeconds}
        accountLabel={getAccountLabel(user)}
        onSignOut={signOut}
      />

      <main id="main-content" className={chrome.mainFrame}>
        <section className={`${chrome.heroBlock} ${shellStyles.pageColumn} ${styles.libraryHero}`}>
          <div>
            <p className={`${chrome.heroEyebrow} ${styles.libraryHeroEyebrow}`}>Briefings</p>
            <h1 className={`${chrome.heroTitle} ${styles.libraryHeroTitle}`}>Your briefing library</h1>
            <p className={`${chrome.heroText} ${styles.libraryHeroText}`}>
              Search, revisit, and trim past briefings without losing the thread back to the original source.
            </p>
          </div>
          <div className={chrome.heroMeta}>
            <span className={chrome.statusPillMuted}>
              {getStatusLabel(loading, shellLoading, briefings.total_count, activeBriefingCount)}
            </span>
          </div>
        </section>

        <section className={`${chrome.surface} ${shellStyles.pageColumn} ${styles.librarySurface}`}>
          <div className={`${chrome.surfaceHeader} ${styles.libraryHeader}`}>
            <div>
              <h2 className={chrome.surfaceTitle}>Library</h2>
              {showLibraryHelper ? <p className={chrome.surfaceText}>{helperText}</p> : null}
            </div>
          </div>

          <div className={styles.controlsGrid}>
            <label className={`${chrome.fieldStack} ${styles.libraryField}`}>
              <span className={`${chrome.fieldLabel} ${styles.mobileHiddenLabel}`}>Search</span>
              <input
                className={`${chrome.input} ${styles.librarySearchInput}`}
                type="search"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Search by title, author, or source"
              />
            </label>

            <label className={`${chrome.fieldStack} ${styles.libraryField}`}>
              <span className={`${chrome.fieldLabel} ${styles.mobileHiddenLabel}`}>Sort</span>
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

          {libraryNotice ? (
            <p className={chrome.inlineStatus} ref={libraryNoticeRef} role="status" tabIndex={-1}>
              {libraryNotice}
            </p>
          ) : null}

          {loading && briefings.items.length === 0 ? (
            <p className={chrome.emptyState} role="status">
              Loading your briefing library…
            </p>
          ) : briefings.items.length === 0 ? (
            <p className={chrome.emptyState}>{helperText}</p>
          ) : (
            <div className={styles.libraryList}>
              {briefings.items.map((entry) => (
                <BriefingLibraryRow
                  confirmingDelete={confirmDeleteSessionId === entry.session_id}
                  deleting={deletingSessionId === entry.session_id}
                  entry={entry}
                  key={entry.session_id}
                  opening={openingSessionId === entry.session_id}
                  onCancelDelete={() => closeDeleteConfirmation(entry.session_id)}
                  onDelete={() => void handleDeleteBriefing(entry)}
                  onOpen={(event) => void openBriefing(event, entry)}
                  onPrefetch={() => prefetchBriefing(entry)}
                  onRequestDelete={() => setConfirmDeleteSessionId(entry.session_id)}
                  setRemoveButtonRef={(node) => {
                    if (node) removeButtonRefs.current.set(entry.session_id, node);
                    else removeButtonRefs.current.delete(entry.session_id);
                  }}
                />
              ))}
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

          {error ? (
            <p className={`${chrome.inlineStatus} ${chrome.inlineStatusError}`} role="alert">
              {error}
            </p>
          ) : null}
        </section>
      </main>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import { createApiClient, getApiBaseUrl, type BriefingSessionResponse } from "@fathom/api-client";

import { getApiErrorCode, getApiErrorMessage } from "../../lib/apiErrors";
import {
  cacheSessionSnapshot,
  captureAuthenticatedRequestScope,
  getCachedSessionSnapshot,
  isAuthenticatedRequestScopeCurrent
} from "../../lib/appDataCache";
import { logger } from "../../lib/logger";
import { readSessionStream, type SessionStreamEvent } from "./sessionStream";
import {
  briefingSessionReducer,
  createInitialSessionUiState,
  isTerminalSessionState,
  type SessionContentDeltaPayload,
  type SessionStatusPayload
} from "./sessionState";

const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 5000;
const RECONCILE_INTERVAL_MS = 4000;
const READY_MARKDOWN_RECONCILE_ATTEMPTS = 12;
const READY_MARKDOWN_RECONCILE_INTERVAL_MS = 2500;

type UseBriefingSessionOptions = {
  accessToken: string | null;
  loading: boolean;
  sessionId: string;
  userId: string | null;
};

export function useBriefingSession({ accessToken, loading, sessionId, userId }: UseBriefingSessionOptions) {
  const cachedSnapshot = useMemo(
    () => (sessionId && userId ? getCachedSessionSnapshot(userId, sessionId) : null),
    [sessionId, userId]
  );
  const [sessionState, dispatchSession] = useReducer(
    briefingSessionReducer,
    cachedSnapshot,
    createInitialSessionUiState
  );
  const [sessionLoadError, setSessionLoadError] = useState<string | null>(null);
  const [sessionLoadErrorCode, setSessionLoadErrorCode] = useState<string | null>(null);
  const [sessionLoadAttempt, setSessionLoadAttempt] = useState(0);
  const lastEventIdRef = useRef<string | null>(null);
  const terminalStateRef = useRef(false);
  const lastStreamActivityRef = useRef(Date.now());

  const { phase, session } = sessionState;

  useEffect(() => {
    if (session && userId) {
      cacheSessionSnapshot(userId, session);
    }
  }, [session, userId]);

  useEffect(() => {
    if (loading || !sessionId || !accessToken || !userId) {
      return;
    }

    lastEventIdRef.current = null;
    lastStreamActivityRef.current = Date.now();
    setSessionLoadError(null);
    setSessionLoadErrorCode(null);

    const prefetchedSnapshot = getCachedSessionSnapshot(userId, sessionId);
    dispatchSession({ type: "reset", snapshot: prefetchedSnapshot });
    terminalStateRef.current = prefetchedSnapshot ? isTerminalSessionState(prefetchedSnapshot.state) : false;

    const abortController = new AbortController();
    const requestScope = captureAuthenticatedRequestScope(userId);
    const api = createApiClient(accessToken);
    const requestIsCurrent = () =>
      !abortController.signal.aborted && isAuthenticatedRequestScopeCurrent(requestScope);

    const handleSessionSnapshot = (snapshot: BriefingSessionResponse) => {
      if (!requestIsCurrent()) return;
      dispatchSession({ type: "snapshot", snapshot });
      terminalStateRef.current ||= isTerminalSessionState(snapshot.state);
      lastStreamActivityRef.current = Date.now();
      setSessionLoadError(null);
      setSessionLoadErrorCode(null);
    };

    const handleStatusUpdate = (status: SessionStatusPayload) => {
      if (!requestIsCurrent()) return;
      dispatchSession({ type: "status", status });
      terminalStateRef.current ||= isTerminalSessionState(status.state);
      lastStreamActivityRef.current = Date.now();
    };

    const handleContentDelta = (contentDelta: SessionContentDeltaPayload) => {
      if (!requestIsCurrent()) return;
      dispatchSession({ type: "content_delta", contentDelta });
      terminalStateRef.current ||= isTerminalSessionState(contentDelta.state);
      lastStreamActivityRef.current = Date.now();
    };

    const handleStreamEvent = (event: SessionStreamEvent) => {
      if (!requestIsCurrent()) return;

      lastEventIdRef.current = event.id;
      lastStreamActivityRef.current = Date.now();
      dispatchSession({ type: "stream_restored" });
      if (event.event === "session.event") return;
      if (event.event === "session.content_delta") {
        handleContentDelta(event.data);
      } else if (event.event === "session.status") {
        handleStatusUpdate(event.data);
      } else {
        handleSessionSnapshot(event.data);
      }

      if (event.event === "session.ready" || event.event === "session.failed") {
        const snapshot = event.data;
        logger.info("web.session_stream.terminal", {
          session_id: sessionId,
          state: snapshot.state,
          event_id: event.id
        });
      }
    };

    const refreshSessionSnapshot = async (blocking = false) => {
      const handleFailure = (error: unknown) => {
        if (!requestIsCurrent()) return;
        logger.warn("web.session_snapshot.refresh_failed", {
          session_id: sessionId,
          blocking,
          error_type: error instanceof Error ? error.name : "UnknownError",
          message: error instanceof Error ? error.message : "Unable to fetch briefing session."
        });
        dispatchSession({ type: "snapshot_load_failed" });
        if (blocking) {
          setSessionLoadError(getApiErrorMessage(error, "Unable to fetch briefing session."));
          setSessionLoadErrorCode(getApiErrorCode(error));
        } else {
          dispatchSession({
            type: "stream_lost",
            notice: "Connection is catching up. Saved progress remains here."
          });
        }
      };

      try {
        const { data, error } = await api.GET("/briefing-sessions/{session_id}", {
          params: { path: { session_id: sessionId } }
        });
        if (!requestIsCurrent()) return null;
        if (error) {
          handleFailure(error);
          return null;
        }
        if (data) {
          handleSessionSnapshot(data);
          dispatchSession({ type: "stream_restored" });
        }
        return data ?? null;
      } catch (error) {
        handleFailure(error);
        return null;
      }
    };

    const streamSession = async () => {
      let snapshot = prefetchedSnapshot;
      if (!snapshot) {
        snapshot = await refreshSessionSnapshot(true);
      } else if (!isTerminalSessionState(snapshot.state)) {
        void refreshSessionSnapshot();
      }

      if (!snapshot) {
        dispatchSession({ type: "snapshot_load_failed" });
        return;
      }
      if (isTerminalSessionState(snapshot.state)) return;

      let reconnectDelay = RECONNECT_BASE_DELAY_MS;
      const reconcileTimer = window.setInterval(() => {
        if (
          !terminalStateRef.current &&
          !abortController.signal.aborted &&
          Date.now() - lastStreamActivityRef.current >= RECONCILE_INTERVAL_MS
        ) {
          void refreshSessionSnapshot();
        }
      }, RECONCILE_INTERVAL_MS);

      try {
        while (!abortController.signal.aborted) {
          try {
            const headers = new Headers({ Accept: "text/event-stream", Authorization: `Bearer ${accessToken}` });
            if (lastEventIdRef.current) headers.set("Last-Event-ID", lastEventIdRef.current);

            const response = await fetch(new URL(snapshot.events_url, getApiBaseUrl()).toString(), {
              headers,
              cache: "no-store",
              signal: abortController.signal
            });
            if (!response.ok || !response.body) {
              logger.warn("web.session_stream.open_failed", {
                session_id: sessionId,
                status_code: response.status,
                last_event_id: lastEventIdRef.current
              });
              throw new Error(`Unable to open the live session stream (${response.status}).`);
            }

            reconnectDelay = RECONNECT_BASE_DELAY_MS;
            dispatchSession({ type: "stream_restored" });
            logger.info("web.session_stream.opened", {
              session_id: sessionId,
              last_event_id: lastEventIdRef.current
            });
            await readSessionStream(response.body, handleStreamEvent);
            if (terminalStateRef.current || abortController.signal.aborted) return;
          } catch (error) {
            if (abortController.signal.aborted) return;
            logger.warn("web.session_stream.error", {
              session_id: sessionId,
              error_type: error instanceof Error ? error.name : "UnknownError",
              message: error instanceof Error ? error.message : "Unknown stream error"
            });
            dispatchSession({
              type: "stream_lost",
              notice:
                error instanceof Error && error.message.includes("live session stream")
                  ? "Connection is catching up. Saved progress remains here."
                  : "Live updates paused for a moment. Reconnecting now."
            });
          }

          if (terminalStateRef.current || abortController.signal.aborted) return;
          await sleep(reconnectDelay, abortController.signal);
          logger.info("web.session_stream.reconnecting", { session_id: sessionId, delay_ms: reconnectDelay });
          reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_DELAY_MS);
        }
      } finally {
        window.clearInterval(reconcileTimer);
      }
    };

    void streamSession().catch((error) => {
      if (abortController.signal.aborted) return;
      logger.warn("web.session_stream.unhandled_error", {
        session_id: sessionId,
        error_type: error instanceof Error ? error.name : "UnknownError",
        message: error instanceof Error ? error.message : "Unexpected session stream error"
      });
      dispatchSession({ type: "stream_lost", notice: "Connection is catching up. Saved progress remains here." });
    });

    return () => abortController.abort();
  }, [accessToken, loading, sessionId, sessionLoadAttempt, userId]);

  useEffect(() => {
    if (!accessToken || !userId || !sessionId || phase !== "delivering") return;

    let attempts = 0;
    let cancelled = false;
    const requestScope = captureAuthenticatedRequestScope(userId);
    const api = createApiClient(accessToken);

    const reconcileReadyMarkdown = async () => {
      attempts += 1;
      const { data, error } = await api.GET("/briefing-sessions/{session_id}", {
        params: { path: { session_id: sessionId } }
      });
      if (cancelled || !isAuthenticatedRequestScopeCurrent(requestScope)) return;

      if (error) {
        logger.warn("web.session.ready_markdown_reconcile_failed", { session_id: sessionId, attempt: attempts });
        if (attempts >= READY_MARKDOWN_RECONCILE_ATTEMPTS) dispatchSession({ type: "delivery_failed" });
        return;
      }
      if (data) dispatchSession({ type: "snapshot", snapshot: data });
      if (!data?.briefing_markdown?.trim() && attempts >= READY_MARKDOWN_RECONCILE_ATTEMPTS) {
        dispatchSession({ type: "delivery_failed" });
      }
    };

    const intervalId = window.setInterval(() => {
      if (attempts >= READY_MARKDOWN_RECONCILE_ATTEMPTS) {
        window.clearInterval(intervalId);
      } else {
        void reconcileReadyMarkdown();
      }
    }, READY_MARKDOWN_RECONCILE_INTERVAL_MS);
    void reconcileReadyMarkdown();

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [accessToken, phase, sessionId, sessionLoadAttempt, userId]);

  const retrySessionLoad = useCallback(() => {
    setSessionLoadError(null);
    setSessionLoadErrorCode(null);
    dispatchSession({ type: "delivery_retry" });
    setSessionLoadAttempt((attempt) => attempt + 1);
  }, []);

  return { dispatchSession, retrySessionLoad, sessionLoadError, sessionLoadErrorCode, sessionState };
}

async function sleep(ms: number, signal: AbortSignal) {
  await new Promise<void>((resolve) => {
    const timeoutId = window.setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, ms);
    const abort = () => {
      window.clearTimeout(timeoutId);
      signal.removeEventListener("abort", abort);
      resolve();
    };
    signal.addEventListener("abort", abort, { once: true });
  });
}

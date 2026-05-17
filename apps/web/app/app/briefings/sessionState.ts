import type { BriefingSessionResponse } from "@fathom/api-client";

export type SessionContentDeltaPayload = {
  session_id: string;
  briefing_id: string | null;
  state: BriefingSessionResponse["state"];
  message: string;
  detail: string | null;
  progress: number;
  source_title: string;
  source_author: string | null;
  source_duration_seconds: number | null;
  source_thumbnail_url: string | null;
  briefing_has_pdf: boolean;
  markdown_length: number;
  delta: string;
};

export type SessionStatusPayload = {
  session_id: string;
  briefing_id: string | null;
  state: BriefingSessionResponse["state"];
  message: string;
  detail: string | null;
  progress: number;
  resolution_type: BriefingSessionResponse["resolution_type"];
  source_title: string;
  source_author: string | null;
  source_duration_seconds: number | null;
  source_thumbnail_url: string | null;
  briefing_has_pdf: boolean;
  error_code: string | null;
  error_message: string | null;
};

export type SessionUiPhase = "loading_session" | "processing" | "streaming" | "delivering" | "ready" | "failed";
export type StreamHealth = "live" | "reconnecting";

export type SessionUiState = {
  connectionNotice: string | null;
  initialSnapshotLoaded: boolean;
  markdown: string;
  phase: SessionUiPhase;
  progress: number;
  session: BriefingSessionResponse | null;
  streamHealth: StreamHealth;
};

export type SessionUiAction =
  | { type: "reset"; snapshot?: BriefingSessionResponse | null }
  | { type: "snapshot"; snapshot: BriefingSessionResponse }
  | { type: "status"; status: SessionStatusPayload }
  | { type: "content_delta"; contentDelta: SessionContentDeltaPayload }
  | { type: "snapshot_load_failed" }
  | { type: "stream_lost"; notice: string }
  | { type: "stream_restored" };

const SESSION_STATE_RANK: Record<BriefingSessionResponse["state"], number> = {
  accepted: 0,
  resolving_source: 1,
  reusing_existing: 2,
  transcribing: 3,
  drafting_briefing: 4,
  finalizing_briefing: 5,
  ready: 6,
  failed: 6
};

export function createInitialSessionUiState(snapshot?: BriefingSessionResponse | null): SessionUiState {
  const markdown = snapshot?.briefing_markdown ?? "";
  const progress = snapshot ? resolveNextProgress(0, snapshot.progress, snapshot.state) : 5;

  return withDerivedPhase({
    connectionNotice: null,
    initialSnapshotLoaded: Boolean(snapshot),
    markdown,
    progress,
    session: snapshot ? { ...snapshot, briefing_markdown: markdown, progress } : null,
    streamHealth: "live"
  });
}

export function briefingSessionReducer(state: SessionUiState, action: SessionUiAction): SessionUiState {
  if (action.type === "reset") {
    return createInitialSessionUiState(action.snapshot);
  }

  if (action.type === "snapshot_load_failed") {
    return withDerivedPhase({
      ...state,
      initialSnapshotLoaded: true
    });
  }

  if (action.type === "stream_lost") {
    return withDerivedPhase({
      ...state,
      connectionNotice: action.notice,
      streamHealth: "reconnecting"
    });
  }

  if (action.type === "stream_restored") {
    return withDerivedPhase({
      ...state,
      connectionNotice: null,
      streamHealth: "live"
    });
  }

  if (action.type === "snapshot") {
    const session = mergeSessionSnapshot(state.session, action.snapshot);
    const markdown = keepLongestMarkdown(state.markdown, session.briefing_markdown ?? "");

    return withDerivedPhase({
      ...state,
      connectionNotice: null,
      initialSnapshotLoaded: true,
      markdown,
      progress: session.progress,
      session,
      streamHealth: "live"
    });
  }

  if (action.type === "status") {
    if (!state.session) {
      return withDerivedPhase({ ...state, initialSnapshotLoaded: true });
    }

    const session = mergeStatusUpdate(state.session, action.status);

    return withDerivedPhase({
      ...state,
      connectionNotice: null,
      initialSnapshotLoaded: true,
      progress: session.progress,
      session,
      streamHealth: "live"
    });
  }

  if (action.type === "content_delta") {
    if (!state.session) {
      return withDerivedPhase({ ...state, initialSnapshotLoaded: true });
    }

    const markdown = appendContentDelta(state.markdown, action.contentDelta);
    const session = mergeContentDelta(state.session, action.contentDelta, markdown);

    return withDerivedPhase({
      ...state,
      connectionNotice: null,
      initialSnapshotLoaded: true,
      markdown,
      progress: session.progress,
      session,
      streamHealth: "live"
    });
  }

  return state;
}

export function isTerminalSessionState(state: BriefingSessionResponse["state"]): boolean {
  return state === "ready" || state === "failed";
}

export function keepLongestMarkdown(current: string, incoming: string): string {
  if (!incoming.trim()) {
    return current;
  }
  if (incoming.length < current.length) {
    return current;
  }
  return incoming;
}

export function resolveNextProgress(
  currentProgress: number,
  incomingProgress: number,
  incomingState: BriefingSessionResponse["state"]
): number {
  const clampedCurrent = Math.max(0, Math.min(currentProgress, 100));
  const clampedIncoming = Math.max(0, Math.min(incomingProgress, 100));
  if (isTerminalSessionState(incomingState)) {
    return 100;
  }
  return Math.max(clampedCurrent, clampedIncoming);
}

function mergeSessionSnapshot(
  current: BriefingSessionResponse | null,
  incoming: BriefingSessionResponse
): BriefingSessionResponse {
  const state = resolveSessionState(current?.state ?? null, incoming.state);
  const markdown = keepLongestMarkdown(current?.briefing_markdown ?? "", incoming.briefing_markdown ?? "");
  const progress = resolveNextProgress(current?.progress ?? 0, incoming.progress, state);

  return {
    ...incoming,
    state,
    progress,
    briefing_markdown: markdown || incoming.briefing_markdown
  };
}

function mergeStatusUpdate(
  current: BriefingSessionResponse,
  status: SessionStatusPayload
): BriefingSessionResponse {
  const state = resolveSessionState(current.state, status.state);

  return {
    ...current,
    briefing_id: status.briefing_id ?? current.briefing_id,
    state,
    message: status.message,
    detail: status.detail,
    progress: resolveNextProgress(current.progress, status.progress, state),
    resolution_type: status.resolution_type,
    source_title: status.source_title,
    source_author: status.source_author,
    source_duration_seconds: status.source_duration_seconds,
    source_thumbnail_url: status.source_thumbnail_url,
    briefing_has_pdf: status.briefing_has_pdf,
    error_code: status.error_code,
    error_message: status.error_message
  };
}

function mergeContentDelta(
  current: BriefingSessionResponse,
  contentDelta: SessionContentDeltaPayload,
  markdown: string
): BriefingSessionResponse {
  const state = resolveSessionState(current.state, contentDelta.state);

  return {
    ...current,
    briefing_id: contentDelta.briefing_id ?? current.briefing_id,
    state,
    message: contentDelta.message,
    detail: contentDelta.detail,
    progress: resolveNextProgress(current.progress, contentDelta.progress, state),
    source_title: contentDelta.source_title,
    source_author: contentDelta.source_author,
    source_duration_seconds: contentDelta.source_duration_seconds,
    source_thumbnail_url: contentDelta.source_thumbnail_url,
    briefing_has_pdf: contentDelta.briefing_has_pdf,
    briefing_markdown: markdown
  };
}

function appendContentDelta(current: string, contentDelta: SessionContentDeltaPayload): string {
  if (contentDelta.markdown_length <= current.length) {
    return current;
  }

  return `${current}${contentDelta.delta}`;
}

function resolveSessionState(
  currentState: BriefingSessionResponse["state"] | null,
  incomingState: BriefingSessionResponse["state"]
): BriefingSessionResponse["state"] {
  if (!currentState) {
    return incomingState;
  }
  if (incomingState === "failed" || currentState === "failed") {
    return "failed";
  }
  if (incomingState === "ready" || currentState === "ready") {
    return "ready";
  }
  return SESSION_STATE_RANK[incomingState] >= SESSION_STATE_RANK[currentState] ? incomingState : currentState;
}

function withDerivedPhase(state: Omit<SessionUiState, "phase">): SessionUiState {
  return {
    ...state,
    phase: deriveSessionUiPhase(state)
  };
}

function deriveSessionUiPhase(state: Omit<SessionUiState, "phase">): SessionUiPhase {
  if (!state.initialSnapshotLoaded) {
    return "loading_session";
  }
  if (state.session?.state === "failed") {
    return "failed";
  }
  if (state.session?.state === "ready" && !state.markdown.trim()) {
    return "delivering";
  }
  if (state.session?.state === "ready") {
    return "ready";
  }
  if (state.markdown.trim()) {
    return "streaming";
  }
  return "processing";
}

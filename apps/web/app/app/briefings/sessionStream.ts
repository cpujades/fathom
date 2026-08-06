import type { BriefingSessionResponse } from "@fathom/api-client";

import type { SessionContentDeltaPayload, SessionStatusPayload } from "./sessionState";

type SessionEventName =
  | "session.snapshot"
  | "session.updated"
  | "session.ready"
  | "session.failed";

export type SessionStreamEvent =
  | { id: string | null; event: "session.event"; data: Record<string, unknown> }
  | { id: string | null; event: "session.content_delta"; data: SessionContentDeltaPayload }
  | { id: string | null; event: "session.status"; data: SessionStatusPayload }
  | { id: string | null; event: SessionEventName; data: BriefingSessionResponse };

export class SessionStreamProtocolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SessionStreamProtocolError";
  }
}

export class SessionStreamStaleError extends Error {
  constructor() {
    super("The live session stream stopped sending transport activity.");
    this.name = "SessionStreamStaleError";
  }
}

type SessionStreamReadOptions = {
  onActivity?: (receivedBytes: number) => Promise<void> | void;
  onStale?: () => Promise<void> | void;
  staleAfterMs?: number;
};

export async function readSessionStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: SessionStreamEvent) => Promise<void> | void,
  options: SessionStreamReadOptions = {}
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await readWithStaleTimeout(reader, options.staleAfterMs);
      if (value?.byteLength) await options.onActivity?.(value.byteLength);
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

      let boundary = findEventBoundary(buffer);
      while (boundary) {
        const parsed = parseSessionStreamEvent(buffer.slice(0, boundary.index));
        buffer = buffer.slice(boundary.index + boundary.length);
        if (parsed) await onEvent(parsed);
        boundary = findEventBoundary(buffer);
      }

      if (done) {
        const parsed = parseSessionStreamEvent(buffer);
        if (parsed) await onEvent(parsed);
        return;
      }
    }
  } catch (error) {
    if (error instanceof SessionStreamStaleError) {
      await options.onStale?.();
      await reader.cancel(error).catch(() => undefined);
    }
    throw error;
  } finally {
    reader.releaseLock();
  }
}

async function readWithStaleTimeout(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  staleAfterMs: number | undefined
): Promise<ReadableStreamReadResult<Uint8Array>> {
  if (!staleAfterMs || staleAfterMs <= 0) return reader.read();

  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      reader.read(),
      new Promise<never>((_resolve, reject) => {
        timeoutId = setTimeout(() => reject(new SessionStreamStaleError()), staleAfterMs);
      })
    ]);
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
}

export function parseSessionStreamEvent(rawEvent: string): SessionStreamEvent | null {
  const trimmed = rawEvent.trim();
  if (!trimmed) return null;

  let id: string | null = null;
  let event = "message";
  const dataLines: string[] = [];

  for (const line of rawEvent.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue;
    const separatorIndex = line.indexOf(":");
    if (separatorIndex === -1) continue;

    const field = line.slice(0, separatorIndex).trim();
    const value = line.slice(separatorIndex + 1).trimStart();
    if (field === "id") id = value;
    else if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }

  const rawData = dataLines.join("\n");
  if (!rawData) return null;

  let data: unknown;
  try {
    data = JSON.parse(rawData);
  } catch {
    throw new SessionStreamProtocolError(`The ${event} event contained invalid JSON.`);
  }

  if (event === "session.event" && isRecord(data)) return { id, event, data };
  if (event === "session.content_delta" && isContentDelta(data)) return { id, event, data };
  if (event === "session.status" && isSessionStatus(data)) return { id, event, data };
  if (isSnapshotEvent(event) && isSessionSnapshot(data)) return { id, event, data };

  throw new SessionStreamProtocolError(`The ${event} event did not match the session stream contract.`);
}

export function isValidSessionEventCursor(value: string | null): value is string {
  return value !== null && /^\d+$/.test(value);
}

export function nextSessionStreamReconnectDelay(currentMs: number, maximumMs: number): number {
  return Math.min(currentMs * 2, maximumMs);
}

function findEventBoundary(buffer: string): { index: number; length: number } | null {
  const match = /\r?\n\r?\n/.exec(buffer);
  return match ? { index: match.index, length: match[0].length } : null;
}

const SESSION_STATES = new Set<BriefingSessionResponse["state"]>([
  "accepted",
  "resolving_source",
  "reusing_existing",
  "transcribing",
  "drafting_briefing",
  "finalizing_briefing",
  "ready",
  "failed"
]);
const RESOLUTION_TYPES = new Set<BriefingSessionResponse["resolution_type"]>([
  "new",
  "joined_existing",
  "reused_ready"
]);
const SNAPSHOT_EVENTS = new Set<SessionEventName>([
  "session.snapshot",
  "session.updated",
  "session.ready",
  "session.failed"
]);

function isSnapshotEvent(value: string): value is SessionEventName {
  return SNAPSHOT_EVENTS.has(value as SessionEventName);
}

function isSessionSnapshot(value: unknown): value is BriefingSessionResponse {
  if (!hasSessionStatusBase(value) || !RESOLUTION_TYPES.has(value.resolution_type as BriefingSessionResponse["resolution_type"])) {
    return false;
  }
  return (
    isString(value.submitted_url) &&
    isString(value.canonical_source_url) &&
    (value.source_type === "youtube" || value.source_type === "url") &&
    isString(value.source_identity_key) &&
    isString(value.source_title) &&
    isString(value.session_url) &&
    isString(value.events_url) &&
    typeof value.briefing_has_pdf === "boolean" &&
    isOptionalNullableString(value.briefing_id) &&
    isOptionalNullableString(value.briefing_markdown) &&
    isOptionalNullableString(value.error_code) &&
    isOptionalNullableString(value.error_message) &&
    isOptionalNullableString(value.source_author) &&
    isOptionalNullableNumber(value.source_duration_seconds) &&
    isOptionalNullableString(value.source_thumbnail_url)
  );
}

function isSessionStatus(value: unknown): value is SessionStatusPayload {
  return (
    hasSessionStatusBase(value) &&
    RESOLUTION_TYPES.has(value.resolution_type as BriefingSessionResponse["resolution_type"]) &&
    isNullableString(value.briefing_id) &&
    isString(value.source_title) &&
    isNullableString(value.source_author) &&
    isNullableNumber(value.source_duration_seconds) &&
    isNullableString(value.source_thumbnail_url) &&
    typeof value.briefing_has_pdf === "boolean" &&
    isNullableString(value.error_code) &&
    isNullableString(value.error_message)
  );
}

function isContentDelta(value: unknown): value is SessionContentDeltaPayload {
  return (
    hasSessionStatusBase(value) &&
    isNullableString(value.briefing_id) &&
    isString(value.source_title) &&
    isNullableString(value.source_author) &&
    isNullableNumber(value.source_duration_seconds) &&
    isNullableString(value.source_thumbnail_url) &&
    typeof value.briefing_has_pdf === "boolean" &&
    typeof value.markdown_length === "number" &&
    isString(value.delta)
  );
}

function hasSessionStatusBase(value: unknown): value is Record<string, unknown> & {
  message: string;
  progress: number;
  session_id: string;
  state: BriefingSessionResponse["state"];
} {
  return (
    isRecord(value) &&
    isString(value.session_id) &&
    SESSION_STATES.has(value.state as BriefingSessionResponse["state"]) &&
    isString(value.message) &&
    typeof value.progress === "number" &&
    isOptionalNullableString(value.detail)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNullableString(value: unknown): value is string | null {
  return value === null || isString(value);
}

function isOptionalNullableString(value: unknown): value is string | null | undefined {
  return value === undefined || isNullableString(value);
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || typeof value === "number";
}

function isOptionalNullableNumber(value: unknown): value is number | null | undefined {
  return value === undefined || isNullableNumber(value);
}

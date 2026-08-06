import assert from "node:assert/strict";
import test from "node:test";

import {
  isValidSessionEventCursor,
  nextSessionStreamReconnectDelay,
  parseSessionStreamEvent,
  readSessionStream,
  SessionStreamProtocolError,
  SessionStreamStaleError
} from "./sessionStream.ts";

const snapshot = {
  session_id: "11111111-1111-4111-8111-111111111111",
  briefing_id: null,
  state: "drafting_briefing",
  message: "Drafting your briefing",
  detail: "Drafting",
  progress: 60,
  resolution_type: "new",
  submitted_url: "https://www.youtube.com/watch?v=test",
  canonical_source_url: "https://www.youtube.com/watch?v=test",
  source_type: "youtube",
  source_identity_key: "youtube:test",
  source_title: "Test briefing",
  source_author: "Test author",
  source_duration_seconds: 600,
  source_thumbnail_url: null,
  session_url: "/briefing-sessions/11111111-1111-4111-8111-111111111111",
  events_url: "/briefing-sessions/11111111-1111-4111-8111-111111111111/events",
  error_code: null,
  error_message: null,
  briefing_markdown: "",
  briefing_has_pdf: false
};

test("parses a validated session snapshot", () => {
  const event = parseSessionStreamEvent(
    `id: 42\nevent: session.snapshot\ndata: ${JSON.stringify(snapshot)}`
  );

  assert.deepEqual(event, { id: "42", event: "session.snapshot", data: snapshot });
});

test("ignores comments while preserving data in the same event block", () => {
  const event = parseSessionStreamEvent(
    `: keepalive\r\nid: 43\r\nevent: session.ready\r\ndata: ${JSON.stringify({
      ...snapshot,
      state: "ready",
      progress: 100
    })}`
  );

  assert.equal(event?.event, "session.ready");
  assert.equal(event?.id, "43");
});

test("rejects malformed JSON and contract violations", () => {
  assert.throws(
    () => parseSessionStreamEvent("event: session.status\ndata: {"),
    SessionStreamProtocolError
  );
  assert.throws(
    () => parseSessionStreamEvent('event: session.status\ndata: {"state":"invented"}'),
    SessionStreamProtocolError
  );
});

test("reads events separated with LF or CRLF across stream chunks", async () => {
  const encoded = new TextEncoder().encode(
    `: keepalive\r\n\r\nid: 44\r\nevent: session.updated\r\ndata: ${JSON.stringify(snapshot)}\r\n\r\n`
  );
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(encoded.slice(0, 17));
      controller.enqueue(encoded.slice(17));
      controller.close();
    }
  });
  const events = [];

  await readSessionStream(stream, (event) => events.push(event));

  assert.equal(events.length, 1);
  assert.equal(events[0].event, "session.updated");
  assert.equal(events[0].id, "44");
});

test("reports keepalive transport activity without inventing a state event", async () => {
  const activity = [];
  const events = [];
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(": keepalive\n\n"));
      controller.close();
    }
  });

  await readSessionStream(stream, (event) => events.push(event), {
    onActivity: (receivedBytes) => activity.push(receivedBytes),
    staleAfterMs: 50
  });

  assert.equal(activity.length, 1);
  assert.ok(activity[0] > 0);
  assert.deepEqual(events, []);
});

test("keepalive activity resets the transport stale deadline", async () => {
  let controller;
  const stream = new ReadableStream({
    start(streamController) {
      controller = streamController;
    }
  });
  const reading = readSessionStream(stream, () => undefined, { staleAfterMs: 50 });

  setTimeout(() => controller.enqueue(new TextEncoder().encode(": keepalive\n\n")), 30);
  setTimeout(() => controller.close(), 60);

  await reading;
});

test("fails a transport that sends no bytes within the stale window", async () => {
  let cancelled = false;
  let staleReported = false;
  const stream = new ReadableStream({
    cancel() {
      cancelled = true;
    }
  });

  await assert.rejects(
    readSessionStream(stream, () => undefined, {
      onStale: () => {
        staleReported = true;
      },
      staleAfterMs: 5
    }),
    SessionStreamStaleError
  );
  assert.equal(staleReported, true);
  assert.equal(cancelled, true);
});

test("only accepts non-negative numeric event cursors for reconnect replay", () => {
  assert.equal(isValidSessionEventCursor("0"), true);
  assert.equal(isValidSessionEventCursor("42"), true);
  assert.equal(isValidSessionEventCursor(null), false);
  assert.equal(isValidSessionEventCursor("-1"), false);
  assert.equal(isValidSessionEventCursor("cursor"), false);
});

test("repeated reconnect failures back off to a fixed upper bound", () => {
  let delay = 1_000;
  delay = nextSessionStreamReconnectDelay(delay, 5_000);
  assert.equal(delay, 2_000);
  delay = nextSessionStreamReconnectDelay(delay, 5_000);
  assert.equal(delay, 4_000);
  delay = nextSessionStreamReconnectDelay(delay, 5_000);
  assert.equal(delay, 5_000);
  assert.equal(nextSessionStreamReconnectDelay(delay, 5_000), 5_000);
});

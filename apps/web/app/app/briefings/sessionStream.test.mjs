import assert from "node:assert/strict";
import test from "node:test";

import {
  parseSessionStreamEvent,
  readSessionStream,
  SessionStreamProtocolError
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

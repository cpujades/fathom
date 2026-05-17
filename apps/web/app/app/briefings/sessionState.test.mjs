import assert from "node:assert/strict";
import test from "node:test";

import { briefingSessionReducer, createInitialSessionUiState } from "./sessionState.ts";

const baseSnapshot = (overrides = {}) => ({
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
  briefing_has_pdf: false,
  ...overrides
});

const statusPayload = (overrides = {}) => ({
  session_id: "11111111-1111-4111-8111-111111111111",
  briefing_id: null,
  state: "drafting_briefing",
  message: "Drafting your briefing",
  detail: "Drafting",
  progress: 65,
  resolution_type: "new",
  source_title: "Test briefing",
  source_author: "Test author",
  source_duration_seconds: 600,
  source_thumbnail_url: null,
  briefing_has_pdf: false,
  error_code: null,
  error_message: null,
  ...overrides
});

const contentDeltaPayload = (overrides = {}) => ({
  session_id: "11111111-1111-4111-8111-111111111111",
  briefing_id: null,
  state: "drafting_briefing",
  message: "Drafting your briefing",
  detail: "Drafting",
  progress: 70,
  source_title: "Test briefing",
  source_author: "Test author",
  source_duration_seconds: 600,
  source_thumbnail_url: null,
  briefing_has_pdf: false,
  markdown_length: 14,
  delta: "First section.",
  ...overrides
});

test("snapshot refreshes cannot move progress backward", () => {
  const state = briefingSessionReducer(createInitialSessionUiState(baseSnapshot({ progress: 65 })), {
    type: "snapshot",
    snapshot: baseSnapshot({ progress: 5 })
  });

  assert.equal(state.progress, 65);
  assert.equal(state.session?.progress, 65);
});

test("status updates cannot move progress backward", () => {
  const state = briefingSessionReducer(createInitialSessionUiState(baseSnapshot({ progress: 65 })), {
    type: "status",
    status: statusPayload({ progress: 30 })
  });

  assert.equal(state.progress, 65);
});

test("empty snapshots cannot erase streamed markdown", () => {
  const stateWithMarkdown = createInitialSessionUiState(
    baseSnapshot({ briefing_markdown: "Visible draft", progress: 70 })
  );
  const state = briefingSessionReducer(stateWithMarkdown, {
    type: "snapshot",
    snapshot: baseSnapshot({ briefing_markdown: "", progress: 72 })
  });

  assert.equal(state.markdown, "Visible draft");
  assert.equal(state.session?.briefing_markdown, "Visible draft");
});

test("content deltas append markdown and enter streaming phase", () => {
  const state = briefingSessionReducer(createInitialSessionUiState(baseSnapshot()), {
    type: "content_delta",
    contentDelta: contentDeltaPayload()
  });

  assert.equal(state.markdown, "First section.");
  assert.equal(state.phase, "streaming");
});

test("ready without markdown stays in delivery phase", () => {
  const state = briefingSessionReducer(createInitialSessionUiState(baseSnapshot({ progress: 92 })), {
    type: "snapshot",
    snapshot: baseSnapshot({ state: "ready", progress: 100, briefing_markdown: "" })
  });

  assert.equal(state.phase, "delivering");
  assert.equal(state.progress, 100);
});

test("stream loss and restore are explicit connection states", () => {
  const reconnecting = briefingSessionReducer(createInitialSessionUiState(baseSnapshot()), {
    type: "stream_lost",
    notice: "Reconnecting"
  });
  const restored = briefingSessionReducer(reconnecting, { type: "stream_restored" });

  assert.equal(reconnecting.streamHealth, "reconnecting");
  assert.equal(reconnecting.connectionNotice, "Reconnecting");
  assert.equal(restored.streamHealth, "live");
  assert.equal(restored.connectionNotice, null);
});

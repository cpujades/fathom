import assert from "node:assert/strict";
import test from "node:test";

import {
  buildMarkdownFilename,
  buildSameSourceRetryHref,
  getDeliveryFailurePresentation,
  getFailurePresentation,
  getFinalizationPresentation,
  isBillingAdmissionErrorCode
} from "./sessionPresentation.ts";
import { getApiErrorCode } from "../../lib/apiErrors.ts";

test("stable admission codes lead to plan-aware billing recovery", () => {
  for (const code of ["insufficient_video_time", "no_video_time", "balance_blocked"]) {
    assert.equal(isBillingAdmissionErrorCode(code), true);
    const presentation = getFailurePresentation(
      { error_code: code, error_message: "Copy may change without changing behavior." },
      null,
      null,
      null,
      true
    );
    assert.equal(presentation.actionHref, "/app/billing?view=packs#billing-offers");
    assert.doesNotMatch(presentation.description, /invalid source/i);
  }
  assert.equal(isBillingAdmissionErrorCode("invalid_request"), false);
});

test("retryable billing finalization does not invite a duplicate run", () => {
  const failure = getFailurePresentation(
    {
      error_code: "usage_settlement_failed",
      error_message: "Usage accounting could not be finalized; retrying shortly."
    },
    null
  );
  const lifecycle = getFinalizationPresentation(
    "usage_settlement_failed",
    "Saving briefing",
    "Saving the finished version."
  );

  assert.equal(failure.actionHref, "/app/briefings");
  assert.match(failure.detail, /Avoid starting a duplicate/);
  assert.equal(lifecycle.label, "Finalizing account usage");
  assert.equal(lifecycle.status, "Retrying");
});

test("provider-stage failures use non-technical recovery copy", () => {
  const transcription = getFailurePresentation(
    { error_code: "transcription_failed", error_message: "Groq request timed out." },
    null
  );
  const summary = getFailurePresentation(
    { error_code: "summary_failed", error_message: "OpenRouter returned an invalid response." },
    null
  );
  const capacity = getFailurePresentation(
    { error_code: "provider_capacity_reached", error_message: "Internal provider detail." },
    null,
    null,
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  );

  assert.equal(transcription.title, "Transcript failed");
  assert.doesNotMatch(transcription.detail, /Groq/);
  assert.equal(summary.title, "Briefing failed");
  assert.doesNotMatch(summary.detail, /OpenRouter/);
  assert.equal(capacity.title, "Talven is handling high demand");
  assert.equal(capacity.description, "Your source is fine.");
  assert.doesNotMatch(`${capacity.description} ${capacity.detail}`, /Groq|OpenRouter|another source/i);
  assert.equal(
    capacity.actionHref,
    "/app/briefings/new?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DdQw4w9WgXcQ&confirm=retry"
  );

  const unavailable = getFailurePresentation(
    { error_code: "provider_temporarily_unavailable", error_message: "Internal provider detail." },
    null,
    null,
    "https://youtu.be/example"
  );
  assert.equal(unavailable.title, "A service is temporarily unavailable");
  assert.doesNotMatch(`${unavailable.description} ${unavailable.detail}`, /high demand/i);
});

test("same-source retries require the explicit confirmation route", () => {
  assert.equal(buildSameSourceRetryHref(null), "/app");
  assert.match(buildSameSourceRetryHref("https://youtu.be/example"), /confirm=retry$/);
});

test("missing and unreadable sessions offer deliberate route recovery", () => {
  const missing = getFailurePresentation(null, "Briefing session not found", "not_found");
  const unavailable = getFailurePresentation(null, "Network request failed");

  assert.equal(missing.actionHref, "/app/briefings");
  assert.equal(missing.title, "Briefing not found");
  assert.equal(unavailable.title, "Could not open this briefing");
  assert.match(unavailable.detail, /try opening it again/i);
});

test("ready delivery recovery explains that retrying is safe", () => {
  const deliveryFailure = getDeliveryFailurePresentation();

  assert.equal(deliveryFailure.title, "Your briefing is ready");
  assert.match(deliveryFailure.detail, /will not create another briefing/i);
  assert.match(deliveryFailure.detail, /use more video time/i);
  assert.equal(deliveryFailure.actionHref, "/app/briefings");
});

test("structured API error codes remain available to route recovery", () => {
  assert.equal(
    getApiErrorCode({
      error: {
        code: "not_found",
        message: "Briefing session not found"
      }
    }),
    "not_found"
  );
  assert.equal(getApiErrorCode({ detail: [{ msg: "Invalid request" }] }), null);
});

test("Markdown exports receive safe, stable filenames", () => {
  assert.equal(buildMarkdownFilename("Why Málaga's Market Changed"), "why-malaga-s-market-changed.md");
  assert.equal(buildMarkdownFilename("../../"), "talven-briefing.md");
  assert.equal(buildMarkdownFilename(null), "talven-briefing.md");
});

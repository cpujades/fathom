import assert from "node:assert/strict";
import test from "node:test";

import {
  getFailurePresentation,
  getFinalizationPresentation,
  isCreditOrPaymentError
} from "./sessionPresentation.ts";
import { getApiErrorCode } from "../../lib/apiErrors.ts";

test("quota and negative-balance admission failures lead to billing recovery", () => {
  for (const message of [
    "Insufficient credits for this video.",
    "You have no remaining credits.",
    "Your account is temporarily blocked due to negative balance. Please top up credits."
  ]) {
    assert.equal(isCreditOrPaymentError(message), true);
    assert.equal(
      getFailurePresentation({ error_code: "invalid_request", error_message: message }, null).actionHref,
      "/app/billing#billing-offers"
    );
  }
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
  const unavailable = getFailurePresentation(
    { error_code: "rate_limit_exceeded", error_message: "Rate limit reached." },
    null
  );

  assert.equal(transcription.title, "Transcript failed");
  assert.doesNotMatch(transcription.detail, /Groq/);
  assert.equal(summary.title, "Briefing failed");
  assert.doesNotMatch(summary.detail, /OpenRouter/);
  assert.equal(unavailable.title, "Service temporarily unavailable");
});

test("missing and unreadable sessions offer deliberate route recovery", () => {
  const missing = getFailurePresentation(null, "Briefing session not found", "not_found");
  const unavailable = getFailurePresentation(null, "Network request failed");

  assert.equal(missing.actionHref, "/app/briefings");
  assert.equal(missing.title, "Briefing not found");
  assert.equal(unavailable.title, "Could not open this briefing");
  assert.match(unavailable.detail, /try opening it again/i);
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

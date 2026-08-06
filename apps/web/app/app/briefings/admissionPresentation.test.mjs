import assert from "node:assert/strict";
import test from "node:test";

import { getAdmissionFailurePresentation } from "./admissionPresentation.ts";
import { getApiErrorCode, getApiErrorDetails } from "../../lib/apiErrors.ts";

test("structured duration admission errors show required and available time", () => {
  const payload = {
    error: {
      code: "insufficient_video_time",
      message: "This video needs more time than is currently available.",
      details: { required_seconds: 2_520, available_seconds: 1_080 }
    }
  };
  const presentation = getAdmissionFailurePresentation(
    getApiErrorCode(payload),
    payload.error.message,
    getApiErrorDetails(payload),
    true
  );

  assert.equal(presentation.title, "More video time needed");
  assert.match(presentation.description, /42m 00s/);
  assert.match(presentation.description, /18m 00s/);
  assert.equal(presentation.billingAction?.href, "/app/billing?view=packs#billing-offers");
});

test("zero time and debt blocks always expose billing recovery without blaming the source", () => {
  const zero = getAdmissionFailurePresentation("no_video_time", "No time.", { available_seconds: 0 }, false);
  const blocked = getAdmissionFailurePresentation("balance_blocked", "Paused.", { debt_seconds: 420 }, true);

  assert.equal(zero.billingAction?.label, "See plans and packs");
  assert.equal(blocked.billingAction?.label, "Add a one-time pack");
  assert.doesNotMatch(zero.description, /invalid|unsupported/i);
  assert.match(blocked.description, /7m 00s/);
});

test("source failures never advertise billing", () => {
  for (const code of ["invalid_request", "source_duration_unknown", "source_too_long"]) {
    const presentation = getAdmissionFailurePresentation(code, "Use a public YouTube URL.", null, true);
    assert.equal(presentation.billingAction, null);
    assert.match(presentation.title, /source|video length|too long/i);
  }
});

test("an over-limit source states the supported maximum", () => {
  const presentation = getAdmissionFailurePresentation(
    "source_too_long",
    "This video is longer than supported.",
    { maximum_seconds: 7_200 },
    false
  );

  assert.equal(presentation.title, "Video is too long");
  assert.match(presentation.description, /2h 00m 00s/);
  assert.equal(presentation.billingAction, null);
});

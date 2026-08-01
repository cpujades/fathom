import assert from "node:assert/strict";
import test from "node:test";

import { getCreationAccessState } from "./usagePresentation.ts";

test("zero credits require a purchase even while the settlement debt buffer is unused", () => {
  assert.deepEqual(
    getCreationAccessState({ debt_seconds: 120, is_blocked: false, total_remaining_seconds: 0 }),
    { canCreate: false, debtSeconds: 120, hasNoCredits: true }
  );
});

test("the authoritative API block flag pauses creation", () => {
  assert.deepEqual(
    getCreationAccessState({ debt_seconds: 600, is_blocked: true, total_remaining_seconds: 0 }),
    { canCreate: false, debtSeconds: 600, hasNoCredits: true }
  );
});

test("an unavailable usage snapshot does not invent a client-side block", () => {
  assert.deepEqual(getCreationAccessState(null), {
    canCreate: true,
    debtSeconds: 0,
    hasNoCredits: false
  });
});

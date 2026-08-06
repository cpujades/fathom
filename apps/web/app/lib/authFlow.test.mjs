import assert from "node:assert/strict";
import test from "node:test";

import { resolveAuthPlanSummary } from "../content/pricing.ts";
import { storeSignInEmail, takeSignInEmail } from "./authEmailTransfer.ts";
import { isExistingAccountAuthError } from "./authErrors.ts";

const expectedPaidPlans = [
  ["starter", "Starter", "$9", "6 hours / month", "monthly"],
  ["pro", "Pro", "$19", "15 hours / month", "monthly"],
  ["agency", "Agency", "$49", "50 hours / month", "monthly"],
  ["trial_pack", "Trial Pack", "$5", "3 hours", "one-time"],
  ["creator_pack", "Creator Pack", "$15", "10 hours", "one-time"],
  ["studio_pack", "Studio Pack", "$50", "40 hours", "one-time"]
];

test("auth context resolves every paid selection from the trusted public catalog", () => {
  for (const [planCode, productName, price, includedTime, paymentCadence] of expectedPaidPlans) {
    assert.deepEqual(resolveAuthPlanSummary("paid", planCode), {
      includedTime,
      paymentCadence,
      planCode,
      price,
      productName
    });
  }
});

test("ordinary, free, malformed, and unknown auth contexts have no product summary", () => {
  for (const context of [
    undefined,
    [null, null],
    ["paid", "free"],
    ["paid", "../../agency"],
    ["paid", "made_up_plan"]
  ]) {
    const [intent, planCode] = context ?? [];
    assert.equal(resolveAuthPlanSummary(intent, planCode), null);
  }
});

test("duplicate-account detection is limited to explicit Supabase error codes", () => {
  assert.equal(isExistingAccountAuthError({ code: "email_exists" }), true);
  assert.equal(isExistingAccountAuthError({ code: "USER_ALREADY_EXISTS" }), true);
  assert.equal(isExistingAccountAuthError({ code: "invalid_credentials" }), false);
  assert.equal(isExistingAccountAuthError({ message: "already exists" }), false);
  assert.equal(isExistingAccountAuthError(null), false);
});

test("the transferred sign-in email is trimmed, consumed once, and never placed in a URL", () => {
  const values = new Map();
  const storage = {
    getItem(key) {
      return values.get(key) ?? null;
    },
    removeItem(key) {
      values.delete(key);
    },
    setItem(key, value) {
      values.set(key, value);
    }
  };

  storeSignInEmail(storage, "  person@example.com  ");
  assert.equal(takeSignInEmail(storage), "person@example.com");
  assert.equal(takeSignInEmail(storage), null);

  storeSignInEmail(storage, "   ");
  assert.equal(takeSignInEmail(storage), null);
});

import assert from "node:assert/strict";
import test from "node:test";

import { resolveAuthPlanSummary } from "../content/pricing.ts";
import { storeSignInEmail, takeSignInEmail } from "./authEmailTransfer.ts";
import { isExistingAccountAuthError } from "./authErrors.ts";

const expectedPaidPlans = [
  ["starter", "Starter", { eur: 900, usd: 1000, gbp: 800 }, "6 hours / month", "monthly"],
  ["pro", "Pro", { eur: 1900, usd: 2200, gbp: 1700 }, "15 hours / month", "monthly"],
  ["agency", "Agency", { eur: 4900, usd: 5600, gbp: 4200 }, "50 hours / month", "monthly"],
  ["trial_pack", "Trial Pack", { eur: 600, usd: 700, gbp: 550 }, "3 hours", "one-time"],
  ["creator_pack", "Creator Pack", { eur: 1800, usd: 2100, gbp: 1600 }, "10 hours", "one-time"],
  ["studio_pack", "Studio Pack", { eur: 6000, usd: 6900, gbp: 5200 }, "40 hours", "one-time"]
];

test("auth context resolves every paid selection from the trusted public catalog", () => {
  for (const [planCode, productName, prices, includedTime, paymentCadence] of expectedPaidPlans) {
    assert.deepEqual(resolveAuthPlanSummary("paid", planCode), {
      includedTime,
      paymentCadence,
      planCode,
      prices,
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

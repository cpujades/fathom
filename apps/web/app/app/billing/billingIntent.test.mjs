import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { packPlans, subscriptionPlans } from "../../content/pricing.ts";
import { resolveBillingOfferMode, resolveRequestedPlan } from "./billingIntent.ts";

const catalog = JSON.parse(
  readFileSync(new URL("../../../../../scripts/polar/plan_contract.json", import.meta.url), "utf8")
);
const plans = catalog.map((plan, index) => ({
  ...plan,
  plan_id: `${String(index + 1).padStart(8, "0")}-0000-4000-8000-000000000000`
}));

test("every public paid option resolves the matching catalog plan by stable code", () => {
  for (const publicPlan of [...subscriptionPlans, ...packPlans].filter((plan) => plan.planCode !== "free")) {
    assert.equal(
      resolveRequestedPlan(plans, "paid", publicPlan.planCode)?.plan_code,
      publicPlan.planCode
    );
  }
});

test("missing, unrelated, and malformed intent cannot select a plan", () => {
  assert.equal(resolveRequestedPlan(plans, null, "creator_pack"), null);
  assert.equal(resolveRequestedPlan(plans, "free", "creator_pack"), null);
  assert.equal(resolveRequestedPlan(plans, "paid", "https://example.com"), null);
  assert.equal(resolveRequestedPlan(plans, "paid", "unknown"), null);
});

test("display names and legacy slugs cannot ambiguously select a plan", () => {
  assert.equal(resolveRequestedPlan(plans, "paid", "creator"), null);
  assert.equal(resolveRequestedPlan(plans, "paid", "trial-pack"), null);
});

test("the billing view parameter can open packs without selecting checkout", () => {
  assert.equal(resolveBillingOfferMode("packs"), "pack");
  assert.equal(resolveBillingOfferMode("subscriptions"), "subscription");
  assert.equal(resolveBillingOfferMode("https://example.com"), "subscription");
  assert.equal(resolveBillingOfferMode(null), "subscription");
});

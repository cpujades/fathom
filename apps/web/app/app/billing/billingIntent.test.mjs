import assert from "node:assert/strict";
import test from "node:test";

import { resolveRequestedPlan } from "./billingIntent.ts";

const plans = [
  {
    plan_id: "11111111-1111-4111-8111-111111111111",
    plan_code: "pack_creator",
    name: "Creator",
    plan_type: "pack"
  },
  {
    plan_id: "22222222-2222-4222-8222-222222222222",
    plan_code: "subscription_starter",
    name: "Starter",
    plan_type: "subscription"
  }
];

test("paid intent resolves a requested plan by its public name", () => {
  assert.equal(resolveRequestedPlan(plans, "paid", "creator")?.name, "Creator");
});

test("paid intent also accepts the stable plan code", () => {
  assert.equal(
    resolveRequestedPlan(plans, "paid", "subscription_starter")?.name,
    "Starter"
  );
});

test("missing, unrelated, and malformed intent cannot select a plan", () => {
  assert.equal(resolveRequestedPlan(plans, null, "creator"), null);
  assert.equal(resolveRequestedPlan(plans, "free", "creator"), null);
  assert.equal(resolveRequestedPlan(plans, "paid", "https://example.com"), null);
  assert.equal(resolveRequestedPlan(plans, "paid", "unknown"), null);
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { packPlans, subscriptionPlans } from "./pricing.ts";
import { buildPaidCheckoutHref } from "../lib/pricingIntent.ts";

const catalog = JSON.parse(
  readFileSync(new URL("../../../../scripts/polar/plans.json", import.meta.url), "utf8")
);
const publicPlans = [...subscriptionPlans, ...packPlans];

test("public pricing uses the exact stable plan codes from the billing catalog", () => {
  assert.deepEqual(
    publicPlans.map((plan) => plan.planCode).sort(),
    catalog.map((plan) => plan.plan_code).sort()
  );

  for (const publicPlan of publicPlans) {
    const catalogPlan = catalog.find((plan) => plan.plan_code === publicPlan.planCode);
    assert.ok(catalogPlan, `Missing catalog plan ${publicPlan.planCode}`);
    assert.equal(publicPlan.price, catalogPlan.amount_cents === 0 ? "$0" : `$${catalogPlan.amount_cents / 100}`);
  }
});

test("paid pricing links preserve exact plan codes through the auth entry URL", () => {
  for (const publicPlan of publicPlans.filter((plan) => plan.planCode !== "free")) {
    const href = new URL(buildPaidCheckoutHref(publicPlan.planCode), "https://talven.example");
    assert.equal(href.pathname, "/signup");
    assert.equal(href.searchParams.get("next"), "/app/billing");
    assert.equal(href.searchParams.get("intent"), "paid");
    assert.equal(href.searchParams.get("plan"), publicPlan.planCode);
  }
});

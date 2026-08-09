import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { packPlans, subscriptionPlans } from "./pricing.ts";
import { buildPaidCheckoutHref } from "../lib/pricingIntent.ts";

const catalog = JSON.parse(
  readFileSync(new URL("../../../../scripts/polar/plan_contract.json", import.meta.url), "utf8")
);
const publicPlans = [...subscriptionPlans, ...packPlans];

const formatCatalogPrice = (catalogPlan) => {
  if (catalogPlan.amount_cents === 0) {
    return "Free";
  }

  const format = (currency, symbol) => {
    const amount = catalogPlan.prices[currency] / 100;
    return `${symbol}${Number.isInteger(amount) ? amount : amount.toFixed(2)}`;
  };

  return [format("eur", "€"), format("usd", "$"), format("gbp", "£")].join(" · ");
};

test("public pricing uses the exact stable plan codes from the billing catalog", () => {
  assert.deepEqual(
    publicPlans.map((plan) => plan.planCode).sort(),
    catalog.map((plan) => plan.plan_code).sort()
  );

  for (const publicPlan of publicPlans) {
    const catalogPlan = catalog.find((plan) => plan.plan_code === publicPlan.planCode);
    assert.ok(catalogPlan, `Missing catalog plan ${publicPlan.planCode}`);
    assert.equal(publicPlan.price, formatCatalogPrice(catalogPlan));
  }
});

test("billing catalog keeps launch expiry, carryover, and localized pricing rules explicit", () => {
  for (const plan of catalog) {
    assert.deepEqual(Object.keys(plan.prices).sort(), ["eur", "gbp", "usd"]);
    assert.equal(plan.prices[plan.currency], plan.amount_cents);
    assert.equal(plan.version, plan.plan_code === "free" ? 1 : 2);

    if (plan.plan_type === "pack") {
      assert.equal(plan.pack_expiry_days, 90);
      assert.equal(plan.rollover_cap_seconds, null);
      continue;
    }

    assert.equal(plan.pack_expiry_days, null);
    assert.equal(
      plan.rollover_cap_seconds,
      plan.plan_code === "free" ? 0 : plan.quota_seconds
    );
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

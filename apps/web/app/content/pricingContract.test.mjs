import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { packPlans, resolvePricingPrices, subscriptionPlans } from "./pricing.ts";
import {
  DEFAULT_PRICING_CURRENCY,
  formatPricingPlanPrice,
  formatPricingPrice,
  resolveLocalePricingCurrency
} from "../lib/pricingCurrency.ts";
import { buildPaidCheckoutHref } from "../lib/pricingIntent.ts";

const catalog = JSON.parse(
  readFileSync(new URL("../../../../scripts/polar/plan_contract.json", import.meta.url), "utf8")
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
    assert.deepEqual(publicPlan.prices, catalogPlan.prices);
    assert.deepEqual(resolvePricingPrices(publicPlan.planCode), publicPlan.prices);
  }

  assert.equal(resolvePricingPrices("unknown"), null);
});

test("pricing displays one selected currency with clean money formatting", () => {
  const trialPack = packPlans.find((plan) => plan.planCode === "trial_pack");
  const starter = subscriptionPlans.find((plan) => plan.planCode === "starter");
  assert.ok(trialPack);
  assert.ok(starter);

  assert.equal(formatPricingPrice(trialPack.prices, "gbp"), "£5.50");
  assert.equal(formatPricingPrice(starter.prices, "eur"), "€9");
  assert.equal(formatPricingPrice(starter.prices, "usd"), "$10");
  assert.equal(formatPricingPlanPrice(starter.prices, "eur", "month"), "€9/month");
  assert.equal(formatPricingPlanPrice(trialPack.prices, "gbp", null), "£5.50");
  assert.equal(formatPricingPlanPrice(subscriptionPlans[0].prices, "usd", "month"), "Free");
});

test("pricing uses the browser locale when its currency is available", () => {
  assert.equal(resolveLocalePricingCurrency("es-ES"), "eur");
  assert.equal(resolveLocalePricingCurrency("en-ES"), "eur");
  assert.equal(resolveLocalePricingCurrency("en-GB"), "gbp");
  assert.equal(resolveLocalePricingCurrency("en-US"), "usd");
  assert.equal(resolveLocalePricingCurrency("en-CA"), DEFAULT_PRICING_CURRENCY);
  assert.equal(resolveLocalePricingCurrency("not_a_locale"), DEFAULT_PRICING_CURRENCY);
});

test("billing catalog keeps launch expiry, carryover, and localized pricing rules explicit", () => {
  for (const plan of catalog) {
    assert.equal(plan.currency, DEFAULT_PRICING_CURRENCY);
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

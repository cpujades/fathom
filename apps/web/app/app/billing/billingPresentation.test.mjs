import assert from "node:assert/strict";
import test from "node:test";

import { applyPendingRefundHold, getDisplayedPacks } from "./billingPresentation.ts";

test("a pending refund immediately removes held pack time from the usable balance", () => {
  const usage = {
    subscription_plan_name: "Free",
    subscription_remaining_seconds: 600,
    pack_remaining_seconds: 1_800,
    total_remaining_seconds: 2_400,
    pack_expires_at: null,
    debt_seconds: 0,
    is_blocked: false
  };

  assert.deepEqual(applyPendingRefundHold(usage, 1_800), {
    ...usage,
    pack_remaining_seconds: 0,
    total_remaining_seconds: 600
  });
});

test("a stale refund response cannot subtract more pack time than is visible", () => {
  const usage = {
    subscription_plan_name: "Free",
    subscription_remaining_seconds: 300,
    pack_remaining_seconds: 120,
    total_remaining_seconds: 420,
    pack_expires_at: null,
    debt_seconds: 0,
    is_blocked: false
  };

  assert.deepEqual(applyPendingRefundHold(usage, 600), {
    ...usage,
    pack_remaining_seconds: 0,
    total_remaining_seconds: 300
  });
});

test("refunded packs leave purchased-pack details but remain available to billing history", () => {
  const packs = [
    { polar_order_id: "paid", status: "paid" },
    { polar_order_id: "pending", status: "refund_pending" },
    { polar_order_id: "refunded", status: "refunded" }
  ];

  assert.deepEqual(
    getDisplayedPacks(packs).map((pack) => pack.polar_order_id),
    ["paid", "pending"]
  );
});

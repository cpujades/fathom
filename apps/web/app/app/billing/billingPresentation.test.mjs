import assert from "node:assert/strict";
import test from "node:test";

import {
  applyPendingRefundHold,
  getDisplayedPacks,
  getUsageBreakdown,
  mergeUsageHistoryEntries
} from "./billingPresentation.ts";

test("usage history shows the exact non-zero settlement sources", () => {
  assert.deepEqual(
    getUsageBreakdown({
      subscription_seconds: 100,
      pack_seconds: 80,
      debt_incurred_seconds: 20
    }),
    [
      { label: "Subscription", seconds: 100 },
      { label: "Pack", seconds: 80 },
      { label: "Debt", seconds: 20 }
    ]
  );
});

test("usage history pagination does not duplicate a settlement after a repeated page", () => {
  const first = { job_id: "job-1", title: "First" };
  const second = { job_id: "job-2", title: "Second" };

  assert.deepEqual(mergeUsageHistoryEntries([first], [first, second]), [first, second]);
});

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

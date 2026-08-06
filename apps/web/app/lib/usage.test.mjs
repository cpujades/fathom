import assert from "node:assert/strict";
import test from "node:test";

import {
  getBillingOffersAction,
  getLowBalanceSeconds,
  isUsageSnapshotStale,
  LOW_BALANCE_WARNING_SECONDS,
  resolveCurrentUsageBalance,
  USAGE_SNAPSHOT_STALE_MS
} from "./usage.ts";

const usage = (remaining, overrides = {}) => ({
  debt_seconds: 0,
  is_blocked: false,
  total_remaining_seconds: remaining,
  ...overrides
});

test("the proactive warning covers only positive balances below ten minutes", () => {
  assert.equal(LOW_BALANCE_WARNING_SECONDS, 600);
  assert.equal(getLowBalanceSeconds(usage(600)), null);
  assert.equal(getLowBalanceSeconds(usage(599)), 599);
  assert.equal(getLowBalanceSeconds(usage(1)), 1);
  assert.equal(getLowBalanceSeconds(usage(0)), null);
});

test("debt and blocked balances retain their stronger recovery states", () => {
  assert.equal(getLowBalanceSeconds(usage(300, { debt_seconds: 1 })), null);
  assert.equal(getLowBalanceSeconds(usage(300, { is_blocked: true })), null);
  assert.equal(getLowBalanceSeconds(null), null);
});

test("billing recovery opens packs first only for an active paid subscription", () => {
  assert.deepEqual(getBillingOffersAction(true), {
    href: "/app/billing?view=packs#billing-offers",
    label: "Add a one-time pack"
  });
  assert.deepEqual(getBillingOffersAction(false), {
    href: "/app/billing#billing-offers",
    label: "See plans and packs"
  });
  assert.deepEqual(getBillingOffersAction(null), getBillingOffersAction(false));
});

test("usage refreshes only after the shared snapshot becomes stale", () => {
  const now = 50_000;
  assert.equal(isUsageSnapshotStale(null, now), true);
  assert.equal(isUsageSnapshotStale({ fetchedAt: now - USAGE_SNAPSHOT_STALE_MS + 1 }, now), false);
  assert.equal(isUsageSnapshotStale({ fetchedAt: now - USAGE_SNAPSHOT_STALE_MS }, now), true);
});

test("a refreshed shared balance replaces the page's older usage snapshot", () => {
  assert.deepEqual(
    resolveCurrentUsageBalance(usage(900), {
      debtSeconds: 0,
      isBlocked: false,
      remainingSeconds: 480
    }),
    usage(480)
  );
  assert.deepEqual(
    resolveCurrentUsageBalance(usage(480), {
      debtSeconds: 600,
      isBlocked: true,
      remainingSeconds: 0
    }),
    usage(0, { debt_seconds: 600, is_blocked: true })
  );
});

test("an incomplete shared refresh never invents balance or debt state", () => {
  const loadedUsage = usage(300, { debt_seconds: 20 });
  assert.equal(
    resolveCurrentUsageBalance(loadedUsage, {
      debtSeconds: null,
      isBlocked: null,
      remainingSeconds: null
    }),
    loadedUsage
  );
});

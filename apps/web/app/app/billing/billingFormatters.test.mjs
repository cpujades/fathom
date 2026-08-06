import assert from "node:assert/strict";
import test from "node:test";

import {
  describePurchaseSync,
  describeRefundSync,
  shouldOfferSyncRefresh
} from "./billingSyncPresentation.ts";

test("confirmed billing operations do not claim stale snapshots are current", () => {
  const purchase = {
    status: "synced",
    snapshotStatus: "unavailable",
    orderLabel: "Creator Pack",
    failureCode: null
  };
  const refund = {
    status: "synced",
    snapshotStatus: "unavailable",
    orderLabel: "Creator Pack",
    failureCode: null
  };

  assert.match(describePurchaseSync(purchase), /confirmed/);
  assert.match(describePurchaseSync(purchase), /could not refresh/);
  assert.doesNotMatch(describePurchaseSync(purchase), /updated below/);
  assert.match(describeRefundSync(refund), /refunded/);
  assert.match(describeRefundSync(refund), /could not refresh/);
  assert.equal(shouldOfferSyncRefresh(purchase), true);
});

test("a successful snapshot refresh permits current billing copy", () => {
  const purchase = {
    status: "synced",
    snapshotStatus: "current",
    orderLabel: "Creator Pack",
    failureCode: null
  };

  assert.match(describePurchaseSync(purchase), /access is updated below/);
  assert.equal(shouldOfferSyncRefresh(purchase), false);
});

test("delayed operation copy distinguishes confirmation from the refreshed snapshot", () => {
  const purchase = {
    status: "delayed",
    snapshotStatus: "current",
    orderLabel: "Creator Pack",
    failureCode: null
  };
  const refund = {
    status: "delayed",
    snapshotStatus: "current",
    orderLabel: "Creator Pack",
    failureCode: null
  };

  assert.match(describePurchaseSync(purchase), /cannot match provider confirmation/);
  assert.match(describePurchaseSync(purchase), /latest billing snapshot/);
  assert.match(describePurchaseSync(purchase), /do not need to pay again/);
  assert.match(describeRefundSync(refund), /cannot match provider confirmation/);
  assert.match(describeRefundSync(refund), /latest billing snapshot/);
  assert.match(describeRefundSync(refund), /do not need to submit it again/);
  assert.equal(shouldOfferSyncRefresh(purchase), true);
});

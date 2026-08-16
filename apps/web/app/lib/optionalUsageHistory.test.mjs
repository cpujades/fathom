import assert from "node:assert/strict";
import test from "node:test";

import { loadOptionalUsageHistory } from "./optionalUsageHistory.ts";

const page = {
  items: [],
  limit: 10,
  offset: 0,
  has_more: false
};

test("usage history returns its page when the optional request succeeds", async () => {
  assert.deepEqual(await loadOptionalUsageHistory(Promise.resolve({ data: page })), {
    data: page,
    unavailable: false
  });
});

test("an API usage-history error does not reject the billing snapshot", async () => {
  assert.deepEqual(await loadOptionalUsageHistory(Promise.resolve({ error: { code: "upstream_error" } })), {
    data: null,
    unavailable: true
  });
});

test("a network usage-history error does not reject the billing snapshot", async () => {
  assert.deepEqual(await loadOptionalUsageHistory(Promise.reject(new Error("network unavailable"))), {
    data: null,
    unavailable: true
  });
});

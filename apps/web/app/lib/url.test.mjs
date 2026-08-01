import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAuthCallbackUrl,
  buildAuthDestinationPath,
  buildSignInPath,
  getSafeAuthIntentContext,
  getSafeNextPath
} from "./url.ts";

test("safe app destinations preserve submitted source URLs", () => {
  const nextPath = "/app/briefings/new?url=https%3A%2F%2Fyoutube.com%2Fwatch%3Fv%3Dtest";

  assert.equal(getSafeNextPath(nextPath), nextPath);
  assert.equal(
    buildSignInPath(nextPath),
    `/signin?next=${encodeURIComponent(nextPath)}`
  );
});

test("external, protocol-relative, and non-app destinations are rejected", () => {
  for (const candidate of [
    "https://attacker.example/app",
    "//attacker.example/app",
    "/signin",
    "javascript:alert(1)"
  ]) {
    assert.equal(getSafeNextPath(candidate), "/app");
  }
});

test("paid intent and plan survive entry, callback, and destination redirects", () => {
  const context = { intent: "paid", plan: "Creator_Pack" };
  const entry = new URL(buildSignInPath("/app/billing", context), "http://localhost");
  const callback = new URL(buildAuthCallbackUrl("/app/billing", context));

  assert.equal(entry.pathname, "/signin");
  assert.equal(entry.searchParams.get("next"), "/app/billing");
  assert.equal(entry.searchParams.get("intent"), "paid");
  assert.equal(entry.searchParams.get("plan"), "creator_pack");
  assert.equal(callback.pathname, "/auth/callback");
  assert.equal(callback.searchParams.get("next"), "/app/billing");
  assert.equal(callback.searchParams.get("intent"), "paid");
  assert.equal(callback.searchParams.get("plan"), "creator_pack");
  assert.equal(
    buildAuthDestinationPath("/app/billing", context),
    "/app/billing?intent=paid&plan=creator_pack"
  );
});

test("unknown intent and unsafe plan values are discarded", () => {
  assert.deepEqual(
    getSafeAuthIntentContext({
      intent: "admin",
      plan: "../../../secrets"
    }),
    {
      intent: null,
      plan: null
    }
  );
  assert.deepEqual(
    getSafeAuthIntentContext({
      intent: "paid",
      plan: "starter&next=https://attacker.example"
    }),
    {
      intent: "paid",
      plan: null
    }
  );
  assert.equal(
    buildAuthDestinationPath("/app/billing?tab=history", {
      intent: "paid",
      plan: "../../../secrets"
    }),
    "/app/billing?tab=history&intent=paid"
  );
});

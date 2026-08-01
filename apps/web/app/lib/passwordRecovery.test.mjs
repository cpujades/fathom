import assert from "node:assert/strict";
import test from "node:test";

import { getPasswordRecoveryErrorMessage, validateRecoveryPassword } from "./authPolicy.ts";
import { buildPasswordRecoveryCallbackUrl } from "./url.ts";

process.env.NEXT_PUBLIC_SITE_URL = "https://app.talven.test";

test("password recovery enforces the published password contract and confirmation", () => {
  assert.equal(
    validateRecoveryPassword("short1", "short1"),
    "Password must be at least 12 characters and include a number."
  );
  assert.equal(
    validateRecoveryPassword("long-without-number", "long-without-number"),
    "Password must be at least 12 characters and include a number."
  );
  assert.equal(
    validateRecoveryPassword("a-secure-pass1", "a-secure-pass2"),
    "Passwords do not match."
  );
  assert.equal(validateRecoveryPassword("a-secure-pass1", "a-secure-pass1"), null);
});

test("recovery callbacks preserve only safe app destinations", () => {
  const callback = new URL(buildPasswordRecoveryCallbackUrl("/app/briefings?sort=oldest"));
  assert.equal(callback.origin, "https://app.talven.test");
  assert.equal(callback.pathname, "/auth/recovery/callback");
  assert.equal(callback.searchParams.get("next"), "/app/briefings?sort=oldest");

  const unsafeCallback = new URL(buildPasswordRecoveryCallbackUrl("https://attacker.example"));
  assert.equal(unsafeCallback.pathname, "/auth/recovery/callback");
  assert.equal(unsafeCallback.searchParams.get("next"), null);
});

test("expired recovery links receive non-technical recovery copy", () => {
  assert.match(getPasswordRecoveryErrorMessage("invalid_or_expired"), /invalid or has expired/i);
});

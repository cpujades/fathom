import assert from "node:assert/strict";
import test from "node:test";

import { getPasswordPolicyError, PASSWORD_REQUIREMENTS_MESSAGE } from "./authPolicy.ts";

test("the shared password policy requires 12 characters and one number", () => {
  assert.equal(getPasswordPolicyError("elevenchars"), PASSWORD_REQUIREMENTS_MESSAGE);
  assert.equal(getPasswordPolicyError("twelveletters"), PASSWORD_REQUIREMENTS_MESSAGE);
  assert.equal(getPasswordPolicyError("secure-pass-1"), null);
});

import assert from "node:assert/strict";
import test from "node:test";

import { formatExploreTopic } from "./format.ts";

test("Explore topics use stable slugs and friendly labels", () => {
  assert.equal(formatExploreTopic("business"), "Business");
  assert.equal(formatExploreTopic("self-improvement"), "Self-improvement");
});

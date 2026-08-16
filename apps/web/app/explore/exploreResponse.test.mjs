import assert from "node:assert/strict";
import test from "node:test";

import { isUnknownExploreTopicResponse } from "./exploreResponse.ts";

test("an invalid Explore topic receives its specific recovery page", () => {
  assert.equal(isUnknownExploreTopicResponse(422, "unknown-topic"), true);
});

test("other Explore failures keep the general recovery page", () => {
  assert.equal(isUnknownExploreTopicResponse(500, "business"), false);
  assert.equal(isUnknownExploreTopicResponse(422, undefined), false);
});

import assert from "node:assert/strict";
import test from "node:test";

import { AuthenticatedDataScopeController } from "./authenticatedDataScope.ts";

function deferred() {
  let resolve;
  const promise = new Promise((next) => {
    resolve = next;
  });
  return { promise, resolve };
}

test("A sign-out followed by B invalidates every scope captured for A", () => {
  const controller = new AuthenticatedDataScopeController();
  controller.reset("user-a");
  const userAScope = controller.capture("user-a");

  controller.reset(null);
  controller.reset("user-b");
  const userBScope = controller.capture("user-b");

  assert.equal(controller.isCurrent(userAScope), false);
  assert.equal(controller.isCurrent(userBScope), true);
  assert.throws(() => controller.capture("user-a"), { name: "AuthenticatedDataScopeChangedError" });
});

test("a late A response cannot commit after a concurrent transition to B", async () => {
  const controller = new AuthenticatedDataScopeController();
  const cache = new Map();
  const responseA = deferred();
  const responseB = deferred();

  controller.reset("user-a");
  const scopeA = controller.capture("user-a");
  const requestA = responseA.promise.then((value) => {
    controller.assertCurrent(scopeA);
    cache.set(scopeA.userId, value);
  });

  controller.reset("user-b");
  cache.clear();
  const scopeB = controller.capture("user-b");
  const requestB = responseB.promise.then((value) => {
    controller.assertCurrent(scopeB);
    cache.set(scopeB.userId, value);
  });

  responseB.resolve("B private data");
  await requestB;
  responseA.resolve("A private data");
  await assert.rejects(requestA, { name: "AuthenticatedDataScopeChangedError" });

  assert.deepEqual([...cache.entries()], [["user-b", "B private data"]]);
});

test("an old-token response cannot commit after a same-user session transition", async () => {
  const controller = new AuthenticatedDataScopeController();
  const cache = new Map();
  const oldResponse = deferred();
  const newResponse = deferred();

  controller.reset("user-a");
  const oldTokenScope = controller.capture("user-a");
  const oldRequest = oldResponse.promise.then((value) => {
    controller.assertCurrent(oldTokenScope);
    cache.set("user-a", value);
  });

  controller.reset("user-a");
  cache.clear();
  const newTokenScope = controller.capture("user-a");
  const newRequest = newResponse.promise.then((value) => {
    controller.assertCurrent(newTokenScope);
    cache.set("user-a", value);
  });

  newResponse.resolve("current-session data");
  await newRequest;
  oldResponse.resolve("stale-session data");
  await assert.rejects(oldRequest, { name: "AuthenticatedDataScopeChangedError" });

  assert.equal(cache.get("user-a"), "current-session data");
});

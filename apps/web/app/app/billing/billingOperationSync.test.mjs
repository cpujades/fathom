import assert from "node:assert/strict";
import test from "node:test";

import {
  BillingOperationReadError,
  handleBillingSyncRefresh,
  manuallyRefreshBillingOperation,
  pollBillingOperation,
  refreshBillingSnapshotAfterOperationCheck
} from "./billingOperationSync.ts";

test("billing operation polling is sequential and stops on success", async () => {
  const controller = new AbortController();
  const waits = [];
  let activeRequests = 0;
  let maxActiveRequests = 0;
  let attempts = 0;

  const result = await pollBillingOperation(
    async () => {
      activeRequests += 1;
      maxActiveRequests = Math.max(maxActiveRequests, activeRequests);
      attempts += 1;
      activeRequests -= 1;
      return {
        operation_id: "00000000-0000-0000-0000-000000000001",
        operation_type: "checkout",
        status: attempts === 3 ? "succeeded" : "pending",
        failure_code: null
      };
    },
    {
      signal: controller.signal,
      delays: [0, 1_000, 2_000, 4_000],
      wait: async (delay) => {
        waits.push(delay);
        return true;
      }
    }
  );

  assert.equal(result.outcome, "terminal");
  assert.deepEqual(waits, [0, 1_000, 2_000]);
  assert.equal(attempts, 3);
  assert.equal(maxActiveRequests, 1);
});

test("billing operation polling times out without claiming failure", async () => {
  const result = await pollBillingOperation(
    async () => ({
      operation_id: "00000000-0000-0000-0000-000000000001",
      operation_type: "refund",
      status: "pending",
      failure_code: null
    }),
    {
      signal: new AbortController().signal,
      delays: [0, 1_000, 2_000],
      wait: async () => true
    }
  );

  assert.equal(result.outcome, "timeout");
  assert.equal(result.operation?.operation_type, "refund");
});

test("billing operation polling stops immediately when aborted", async () => {
  const controller = new AbortController();
  controller.abort();
  let attempts = 0;

  const result = await pollBillingOperation(
    async () => {
      attempts += 1;
      return null;
    },
    { signal: controller.signal }
  );

  assert.deepEqual(result, { outcome: "aborted" });
  assert.equal(attempts, 0);
});

test("billing operation polling bounds a read that never settles", async () => {
  let readSignal;
  const result = await pollBillingOperation(
    (signal) => {
      readSignal = signal;
      return new Promise(() => {});
    },
    {
      signal: new AbortController().signal,
      delays: [0],
      readTimeoutMs: 5,
      wait: async () => true
    }
  );

  assert.equal(result.outcome, "timeout");
  assert.equal(readSignal.aborted, true);
});

test("aborting polling cancels the active operation read", async () => {
  const controller = new AbortController();
  let readAborted = false;
  let markReadStarted;
  const readStarted = new Promise((resolve) => {
    markReadStarted = resolve;
  });
  const polling = pollBillingOperation(
    (signal) => new Promise((resolve) => {
      markReadStarted();
      signal.addEventListener("abort", () => {
        readAborted = true;
        resolve(null);
      }, { once: true });
    }),
    { signal: controller.signal, delays: [0], readTimeoutMs: 1_000, wait: async () => true }
  );

  await readStarted;
  controller.abort();
  assert.deepEqual(await polling, { outcome: "aborted" });
  assert.equal(readAborted, true);
});

test("only retryable operation read failures consume another attempt", async () => {
  let attempts = 0;
  const result = await pollBillingOperation(
    async () => {
      attempts += 1;
      if (attempts === 1) throw new BillingOperationReadError("temporary", true);
      return {
        operation_id: "00000000-0000-0000-0000-000000000001",
        operation_type: "checkout",
        status: "succeeded",
        failure_code: null
      };
    },
    { signal: new AbortController().signal, delays: [0, 0], wait: async () => true }
  );

  assert.equal(result.outcome, "terminal");
  assert.equal(attempts, 2);
});

test("terminal operation read failures stop polling immediately", async () => {
  let attempts = 0;
  const error = new BillingOperationReadError("forbidden", false);
  const result = await pollBillingOperation(
    async () => {
      attempts += 1;
      throw error;
    },
    { signal: new AbortController().signal, delays: [0, 0, 0], wait: async () => true }
  );

  assert.equal(result.outcome, "read_failed");
  assert.equal(result.error, error);
  assert.equal(attempts, 1);
});

test("manual refresh checks the operation once before refreshing the authoritative snapshot", async () => {
  const events = [];
  let operationReads = 0;
  let operationResult;
  let snapshotRefreshes = 0;
  const target = { operationId: "00000000-0000-0000-0000-000000000001" };

  await handleBillingSyncRefresh({
    target,
    refreshOperation: async (receivedTarget, mode) => {
      assert.equal(receivedTarget, target);
      assert.equal(mode, "manual");
      operationResult = await manuallyRefreshBillingOperation(
        async () => {
          operationReads += 1;
          events.push("operation");
          return {
            operation_id: target.operationId,
            operation_type: "checkout",
            status: "pending",
            failure_code: null
          };
        },
        async () => {
          snapshotRefreshes += 1;
          events.push("snapshot");
          return { usage: "latest", account: "latest" };
        },
        {
          signal: new AbortController().signal,
          onBeforeSnapshotRefresh: () => events.push("before_snapshot")
        }
      );
    },
    refreshSnapshot: async () => {
      assert.fail("The active-operation path must not start a second snapshot refresh.");
    },
    onSnapshotStatus: () => {
      assert.fail("The active-operation path owns its snapshot status updates.");
    }
  });

  assert.equal(operationResult.outcome, "timeout");
  assert.equal(operationResult.snapshotStatus, "current");
  assert.equal(operationReads, 1);
  assert.equal(snapshotRefreshes, 1);
  assert.deepEqual(events, ["operation", "before_snapshot", "snapshot"]);
});

test("manual refresh without an active operation refreshes snapshot state once", async () => {
  const statuses = [];
  let snapshotRefreshes = 0;

  await handleBillingSyncRefresh({
    target: null,
    refreshOperation: async () => {
      assert.fail("No operation should be checked without an active target.");
    },
    refreshSnapshot: async () => {
      snapshotRefreshes += 1;
      return { usage: "latest", account: "latest" };
    },
    onSnapshotStatus: (status) => statuses.push(status)
  });

  assert.equal(snapshotRefreshes, 1);
  assert.deepEqual(statuses, ["refreshing", "current"]);
});

test("an operation read failure refreshes billing without claiming confirmation", async () => {
  const readError = new BillingOperationReadError("not found", false);
  const result = await pollBillingOperation(
    async () => {
      throw readError;
    },
    {
      signal: new AbortController().signal,
      delays: [0],
      wait: async () => true
    }
  );
  assert.equal(result.outcome, "read_failed");

  let snapshotRefreshes = 0;
  const refreshed = await refreshBillingSnapshotAfterOperationCheck(result, async () => {
    snapshotRefreshes += 1;
    return null;
  });

  assert.equal(refreshed.outcome, "read_failed");
  assert.equal(refreshed.snapshotStatus, "unavailable");
  assert.equal(snapshotRefreshes, 1);
  assert.equal(refreshed.error, readError);
});

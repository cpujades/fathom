import type { BillingSyncOperationResponse } from "@fathom/api-client";

const BILLING_OPERATION_BACKOFF_MS = [0, 1_000, 2_000, 4_000, 5_000, 5_000, 5_000, 5_000, 5_000, 5_000, 5_000, 5_000] as const;
const BILLING_OPERATION_READ_TIMEOUT_MS = 5_000;

export type BillingOperationPollResult =
  | { outcome: "terminal"; operation: BillingSyncOperationResponse }
  | { outcome: "timeout"; operation: BillingSyncOperationResponse | null }
  | { outcome: "read_failed"; error: unknown; operation: BillingSyncOperationResponse | null }
  | { outcome: "aborted" };

export type CompletedBillingOperationPoll = Exclude<BillingOperationPollResult, { outcome: "aborted" }>;

export type BillingOperationPollWithSnapshot = CompletedBillingOperationPoll & {
  snapshotStatus: "current" | "unavailable";
};

type PollOptions = {
  signal: AbortSignal;
  delays?: readonly number[];
  readTimeoutMs?: number;
  onOperation?: (operation: BillingSyncOperationResponse) => void;
  wait?: (delayMs: number, signal: AbortSignal) => Promise<boolean>;
  isRetryableError?: (error: unknown) => boolean;
};

type BillingOperationRefreshOptions = PollOptions & {
  onBeforeSnapshotRefresh?: (result: CompletedBillingOperationPoll) => void;
  shouldRefreshSnapshot?: () => boolean;
};

export type BillingOperationRefreshResult = BillingOperationPollWithSnapshot | { outcome: "aborted" };

export class BillingOperationReadError extends Error {
  readonly retryable: boolean;

  constructor(message: string, retryable: boolean) {
    super(message);
    this.name = "BillingOperationReadError";
    this.retryable = retryable;
  }
}

type ReadAttempt =
  | { outcome: "loaded"; operation: BillingSyncOperationResponse | null }
  | { outcome: "timed_out" }
  | { outcome: "aborted" }
  | { outcome: "failed"; error: unknown };

async function readOperation(
  loadOperation: (signal: AbortSignal) => Promise<BillingSyncOperationResponse | null>,
  signal: AbortSignal,
  timeoutMs: number
): Promise<ReadAttempt> {
  if (signal.aborted) return { outcome: "aborted" };

  const readController = new AbortController();
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  let settleCancellation: ((result: ReadAttempt) => void) | null = null;
  const cancellation = new Promise<ReadAttempt>((resolve) => {
    settleCancellation = resolve;
  });
  const handleAbort = () => {
    readController.abort();
    settleCancellation?.({ outcome: "aborted" });
  };
  signal.addEventListener("abort", handleAbort, { once: true });
  timeoutId = setTimeout(() => {
    readController.abort();
    settleCancellation?.({ outcome: "timed_out" });
  }, timeoutMs);

  try {
    const loaded: Promise<ReadAttempt> = Promise.resolve()
      .then(() => loadOperation(readController.signal))
      .then(
        (operation): ReadAttempt => ({ outcome: "loaded", operation }),
        (error: unknown): ReadAttempt => ({ outcome: "failed", error })
      );
    return await Promise.race([loaded, cancellation]);
  } finally {
    if (timeoutId !== null) clearTimeout(timeoutId);
    signal.removeEventListener("abort", handleAbort);
  }
}

const waitForDelay = (delayMs: number, signal: AbortSignal): Promise<boolean> => {
  if (signal.aborted) return Promise.resolve(false);
  if (delayMs === 0) return Promise.resolve(true);

  return new Promise((resolve) => {
    const timeoutId = window.setTimeout(() => {
      signal.removeEventListener("abort", handleAbort);
      resolve(true);
    }, delayMs);
    const handleAbort = () => {
      window.clearTimeout(timeoutId);
      resolve(false);
    };
    signal.addEventListener("abort", handleAbort, { once: true });
  });
};

export async function pollBillingOperation(
  loadOperation: (signal: AbortSignal) => Promise<BillingSyncOperationResponse | null>,
  {
    signal,
    delays = BILLING_OPERATION_BACKOFF_MS,
    readTimeoutMs = BILLING_OPERATION_READ_TIMEOUT_MS,
    onOperation,
    wait = waitForDelay,
    isRetryableError = (error) => error instanceof BillingOperationReadError && error.retryable
  }: PollOptions
): Promise<BillingOperationPollResult> {
  let latestOperation: BillingSyncOperationResponse | null = null;
  for (const delayMs of delays) {
    if (!(await wait(delayMs, signal))) return { outcome: "aborted" };

    const read = await readOperation(loadOperation, signal, readTimeoutMs);
    if (read.outcome === "aborted") return { outcome: "aborted" };
    if (read.outcome === "failed") {
      if (!isRetryableError(read.error)) {
        return { outcome: "read_failed", error: read.error, operation: latestOperation };
      }
      continue;
    }
    if (read.outcome === "timed_out") continue;

    const { operation } = read;
    if (operation) {
      latestOperation = operation;
      onOperation?.(operation);
    }
    if (operation && operation.status !== "pending") {
      return { outcome: "terminal", operation };
    }
  }

  return signal.aborted ? { outcome: "aborted" } : { outcome: "timeout", operation: latestOperation };
}

export async function refreshBillingSnapshotAfterOperationCheck(
  result: CompletedBillingOperationPoll,
  refreshSnapshot: () => Promise<unknown | null>
): Promise<BillingOperationPollWithSnapshot> {
  const snapshot = await refreshSnapshot();
  return { ...result, snapshotStatus: snapshot ? "current" : "unavailable" };
}

export async function pollBillingOperationAndRefreshSnapshot(
  loadOperation: (signal: AbortSignal) => Promise<BillingSyncOperationResponse | null>,
  refreshSnapshot: () => Promise<unknown | null>,
  {
    onBeforeSnapshotRefresh,
    shouldRefreshSnapshot,
    ...pollOptions
  }: BillingOperationRefreshOptions
): Promise<BillingOperationRefreshResult> {
  const result = await pollBillingOperation(loadOperation, pollOptions);
  if (result.outcome === "aborted" || shouldRefreshSnapshot?.() === false) {
    return { outcome: "aborted" };
  }

  onBeforeSnapshotRefresh?.(result);
  return refreshBillingSnapshotAfterOperationCheck(result, refreshSnapshot);
}

export async function manuallyRefreshBillingOperation(
  loadOperation: (signal: AbortSignal) => Promise<BillingSyncOperationResponse | null>,
  refreshSnapshot: () => Promise<unknown | null>,
  options: Omit<BillingOperationRefreshOptions, "delays">
): Promise<BillingOperationRefreshResult> {
  return pollBillingOperationAndRefreshSnapshot(loadOperation, refreshSnapshot, {
    ...options,
    delays: [0]
  });
}

type BillingSyncRefreshOptions<T> = {
  target: T | null;
  refreshOperation: (target: T, mode: "manual") => Promise<void>;
  refreshSnapshot: () => Promise<unknown | null>;
  onSnapshotStatus: (status: "refreshing" | "current" | "unavailable") => void;
};

export async function handleBillingSyncRefresh<T>({
  target,
  refreshOperation,
  refreshSnapshot,
  onSnapshotStatus
}: BillingSyncRefreshOptions<T>): Promise<void> {
  if (target) {
    await refreshOperation(target, "manual");
    return;
  }

  onSnapshotStatus("refreshing");
  const snapshot = await refreshSnapshot();
  onSnapshotStatus(snapshot ? "current" : "unavailable");
}

export function setBillingOperationInUrl(operationId: string | null): void {
  const url = new URL(window.location.href);
  if (operationId) url.searchParams.set("billing_operation", operationId);
  else {
    url.searchParams.delete("billing_operation");
    url.searchParams.delete("checkout");
    url.searchParams.delete("customer_session_token");
  }
  window.history.replaceState(window.history.state, "", url);
}

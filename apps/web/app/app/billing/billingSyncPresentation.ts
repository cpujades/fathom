type BillingSyncPresentationState = {
  status: "syncing" | "synced" | "failed" | "delayed";
  snapshotStatus: "idle" | "refreshing" | "current" | "unavailable";
  orderLabel: string | null;
};

export function describePurchaseSync(state: BillingSyncPresentationState): string {
  if (state.status === "syncing") {
    return "Payment received. We are updating your video-time balance now.";
  }
  if (state.status === "delayed") {
    if (state.snapshotStatus === "current") {
      return "Payment succeeded, but Talven cannot match provider confirmation to this browser operation yet. Your balance, subscription, and orders below reflect the latest billing snapshot. You do not need to pay again.";
    }
    if (state.snapshotStatus === "refreshing") {
      return "Payment succeeded, but provider confirmation is still delayed. Refreshing your billing details now. You do not need to pay again.";
    }
    if (state.snapshotStatus === "unavailable") {
      return "Payment succeeded, but provider confirmation is still delayed and Talven could not refresh the billing details below. You do not need to pay again.";
    }
    return "Payment succeeded, but provider confirmation is taking longer than expected. You do not need to pay again.";
  }
  if (state.status === "failed") {
    return state.snapshotStatus === "unavailable"
      ? "Talven could not complete this billing update or refresh the details below. Review your billing account before trying again."
      : "Talven could not complete this billing update. Review your billing account before trying again.";
  }
  if (state.snapshotStatus === "current") {
    return `${state.orderLabel ?? "Your purchase"} is confirmed and your access is updated below.`;
  }
  if (state.snapshotStatus === "refreshing") {
    return `${state.orderLabel ?? "Your purchase"} is confirmed. Refreshing your access details now.`;
  }
  return `${state.orderLabel ?? "Your purchase"} is confirmed, but Talven could not refresh the access details below.`;
}

export function describeRefundSync(state: BillingSyncPresentationState): string {
  if (state.status === "syncing") {
    return `Refund requested for ${state.orderLabel ?? "this pack"}. Waiting for provider confirmation now.`;
  }
  if (state.status === "delayed") {
    if (state.snapshotStatus === "current") {
      return "The refund request was accepted, but Talven cannot match provider confirmation to this browser operation yet. Your balance and orders below reflect the latest billing snapshot. You do not need to submit it again.";
    }
    if (state.snapshotStatus === "refreshing") {
      return "The refund request was accepted, but provider confirmation is still delayed. Refreshing your billing details now. You do not need to submit it again.";
    }
    if (state.snapshotStatus === "unavailable") {
      return "The refund request was accepted, but provider confirmation is still delayed and Talven could not refresh the billing details below. You do not need to submit it again.";
    }
    return "The refund request was accepted, but confirmation is still arriving from the provider. You do not need to submit it again.";
  }
  if (state.status === "failed") {
    return state.snapshotStatus === "unavailable"
      ? "The refund was not completed, and Talven could not refresh the billing details below. Review your billing account before trying again."
      : "The refund was not completed. Your billing details are refreshed below; review them before trying again.";
  }
  if (state.snapshotStatus === "current") {
    return `${state.orderLabel ?? "This pack"} is now marked refunded.`;
  }
  if (state.snapshotStatus === "refreshing") {
    return `${state.orderLabel ?? "This pack"} was refunded. Refreshing your billing details now.`;
  }
  return `${state.orderLabel ?? "This pack"} was refunded, but Talven could not refresh the billing details below.`;
}

export function shouldOfferSyncRefresh(state: BillingSyncPresentationState): boolean {
  return state.status === "delayed" || state.snapshotStatus === "unavailable";
}

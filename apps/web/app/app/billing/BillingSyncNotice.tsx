import type { PurchaseSyncState, RefundSyncState } from "./billingFormatters";
import { describePurchaseSync, describeRefundSync, shouldOfferSyncRefresh } from "./billingSyncPresentation";
import chrome from "../../components/app-chrome";
import styles from "./billing-page.module.css";

type BillingSyncNoticeProps = {
  kind: "purchase" | "refund";
  state: PurchaseSyncState | RefundSyncState;
  refreshLoading: boolean;
  onRefresh: () => void;
};

export function BillingSyncNotice({ kind, state, refreshLoading, onRefresh }: BillingSyncNoticeProps) {
  const message = kind === "purchase" ? describePurchaseSync(state) : describeRefundSync(state);
  const refreshLabel = state.status === "delayed"
    ? "Refresh status and billing details"
    : state.snapshotStatus === "unavailable"
      ? "Refresh billing details"
      : "Refresh status";

  return (
    <section
      className={`${chrome.notice} ${styles.pageColumn} ${
        state.status === "failed"
          ? chrome.noticeError
          : state.status === "delayed"
            ? chrome.noticeWarning
            : chrome.noticeInfo
      }`}
      role="status"
      aria-live="polite"
    >
      <h2 className={chrome.noticeTitle}>{kind === "purchase" ? "Purchase status" : "Refund status"}</h2>
      <p className={chrome.noticeText}>{message}</p>
      {shouldOfferSyncRefresh(state) ? (
        <div className={chrome.actionRow}>
          <button
            className={chrome.secondaryButton}
            type="button"
            onClick={onRefresh}
            disabled={refreshLoading}
          >
            {refreshLoading ? "Refreshing billing details..." : refreshLabel}
          </button>
        </div>
      ) : null}
    </section>
  );
}

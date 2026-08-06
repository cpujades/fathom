"use client";

import { Suspense } from "react";
import Link from "next/link";
import * as Dialog from "@radix-ui/react-dialog";
import type { BillingOrderHistoryEntry, PackBillingState } from "@fathom/api-client";

import { AppShellHeader } from "../../components/AppShellHeader";
import { useAppShell } from "../../components/AppShellProvider";
import chrome from "../../components/app-chrome";
import dialogStyles from "./billing-dialog.module.css";
import pageStyles from "./billing-page.module.css";
import { formatDate, formatDuration } from "../../lib/format";
import { getAccountLabel } from "../../lib/accountLabel";
import { BillingSyncNotice } from "./BillingSyncNotice";
import { formatPrice, getPlanBadge, getStatusTone } from "./billingFormatters";
import { useBillingController } from "./useBillingController";

const styles = { ...pageStyles, ...dialogStyles };

function BillingPageContent() {
  const {
    accessNote, account, activePackCount, canManageBilling, checkoutLoading, closeRefundDialog, displayedPacks,
    error, handleCheckout, handleConfirmRefund, handlePortal, handleRefreshSyncStatus, loading, offerMode,
    portalLoading, purchaseSync, quotaAvailablePercent, quotaCapacitySeconds, refundLoading, refundSync,
    refundTarget, remainingSeconds, requestedPlan, selectRefundTarget, setOfferMode, shellLoading, signOut,
    subscriptionStatusText, syncRefreshLoading, usage, user, visiblePlanGroup
  } = useBillingController();

  if (loading) {
    return (
      <div className={chrome.pageFrame}>
        <AppShellHeader
          active="billing"
          remainingSeconds={remainingSeconds}
          accountLabel={getAccountLabel(user)}
          onSignOut={signOut}
        />
        <main id="main-content" className={chrome.mainFrame}>
          <section className={chrome.surface} aria-busy="true">
            <h1 className={chrome.surfaceTitle}>Loading your access...</h1>
            <p className={chrome.surfaceText} role="status">Fetching plans, balances, and billing details.</p>
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader
        active="billing"
        remainingSeconds={remainingSeconds}
        accountLabel={getAccountLabel(user)}
        onSignOut={signOut}
      />

      <main id="main-content" className={chrome.mainFrame}>
        <section className={`${chrome.heroBlock} ${styles.pageColumn}`}>
          <div>
            <p className={chrome.heroEyebrow}>Billing</p>
            <h1 className={chrome.heroTitle}>Your access</h1>
            <p className={chrome.heroText}>See how much video time you have now, then add more when you need it.</p>
          </div>
          <div className={chrome.heroActions}>
            {canManageBilling ? (
              <button className={chrome.primaryButton} type="button" onClick={handlePortal} disabled={portalLoading || shellLoading}>
                {portalLoading ? "Opening portal..." : "Manage plan"}
              </button>
            ) : (
              <a className={chrome.primaryButton} href="#billing-offers">
                Get more video time
              </a>
            )}
            <Link className={chrome.secondaryButton} href="/app">
              Back to workspace
            </Link>
          </div>
        </section>

        {purchaseSync ? (
          <BillingSyncNotice
            kind="purchase"
            state={purchaseSync}
            refreshLoading={syncRefreshLoading}
            onRefresh={() => void handleRefreshSyncStatus()}
          />
        ) : null}

        {refundSync ? (
          <BillingSyncNotice
            kind="refund"
            state={refundSync}
            refreshLoading={syncRefreshLoading}
            onRefresh={() => void handleRefreshSyncStatus()}
          />
        ) : null}

        {error ? (
          <section className={`${chrome.notice} ${styles.pageColumn} ${chrome.noticeError}`} role="alert">
            <h2 className={chrome.noticeTitle}>Billing action failed</h2>
            <p className={chrome.noticeText}>{error}</p>
          </section>
        ) : null}

        {requestedPlan ? (
          <section className={`${chrome.notice} ${styles.pageColumn} ${chrome.noticeInfo}`} role="status">
            <h2 className={chrome.noticeTitle}>{requestedPlan.name} is ready to review</h2>
            <p className={chrome.noticeText}>
              Your choice stayed with you after sign-in. Review the details below before opening secure checkout.
            </p>
          </section>
        ) : null}

        <section className={`${chrome.surface} ${styles.pageColumn} ${styles.accessSection}`}>
          <div className={chrome.surfaceHeader}>
            <div>
              <h2 className={chrome.surfaceTitle}>Current access</h2>
              <p className={chrome.surfaceText}>What you have now, with room to add more only when you need it.</p>
            </div>
            <span className={getStatusTone(account?.subscription.status ?? null)}>{subscriptionStatusText}</span>
          </div>

          {usage && usage.debt_seconds > 0 ? (
            <div
              className={`${chrome.notice} ${usage.is_blocked ? chrome.noticeWarning : chrome.noticeInfo}`}
              role={usage.is_blocked ? "alert" : "status"}
            >
              <h3 className={chrome.noticeTitle}>{usage.is_blocked ? "Briefing creation paused" : "Outstanding balance"}</h3>
              <p className={chrome.noticeText}>
                {formatDuration(usage.debt_seconds)} is owed. New credits repay this amount first.
                {usage.is_blocked ? " Add video time to continue creating briefings." : " Talven checks each source length before starting."}
              </p>
            </div>
          ) : null}

          {usage && quotaAvailablePercent !== null ? (
            <div className={styles.accessMeter}>
              <div className={styles.accessMeterHeader}>
                <span>Video-time balance</span>
                <span>{quotaAvailablePercent}% available</span>
              </div>
              <div
                className={styles.accessMeterTrack}
                role="progressbar"
                aria-label="Available video time"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={quotaAvailablePercent}
              >
                <span className={styles.accessMeterFill} style={{ width: `${quotaAvailablePercent}%` }} />
              </div>
              <p className={styles.accessMeterText}>
                <span className={styles.accessMeterValue}>{formatDuration(usage.total_remaining_seconds)}</span> left of{" "}
                <span className={styles.accessMeterValue}>{formatDuration(quotaCapacitySeconds)}</span> current allowance.
              </p>
            </div>
          ) : null}

          <div className={styles.accessSummary}>
            <article className={styles.accessStat}>
              <p className={styles.accessLabel}>Available time</p>
              <p className={styles.accessValue}>{usage ? formatDuration(usage.total_remaining_seconds) : "-"}</p>
            </article>
            <article className={styles.accessStat}>
              <p className={styles.accessLabel}>Current plan</p>
              <p className={styles.accessValue}>{account?.subscription.plan_name ?? usage?.subscription_plan_name ?? "Free"}</p>
              <p className={styles.accessHint}>{subscriptionStatusText}</p>
            </article>
            <article className={styles.accessStat}>
              <p className={styles.accessLabel}>One-time pack balance</p>
              <p className={styles.accessValue}>{formatDuration(usage?.pack_remaining_seconds ?? 0)}</p>
              <p className={styles.accessHint}>
                {(usage?.pack_remaining_seconds ?? 0) > 0 ? `Expires ${formatDate(usage?.pack_expires_at ?? null)}` : "Add packs anytime"}
              </p>
            </article>
          </div>

          <p className={styles.accessNote}>{accessNote}</p>
        </section>

        <section className={`${chrome.surface} ${styles.pageColumn} ${styles.offerSection}`} id="billing-offers">
          <div className={chrome.surfaceHeader}>
            <div>
              <h2 className={chrome.surfaceTitle}>Get more video time</h2>
              <p className={chrome.surfaceText}>
                Choose a monthly subscription or add a one-time video-time pack when you need it.
              </p>
            </div>
          </div>

          <div className={styles.offerSwitch} role="group" aria-label="Billing offer type">
            <button
              className={`${styles.offerSwitchButton} ${offerMode === "subscription" ? styles.offerSwitchButtonActive : ""}`}
              type="button"
              aria-pressed={offerMode === "subscription"}
              onClick={() => setOfferMode("subscription")}
            >
              <span className={styles.offerSwitchLabel}>Monthly subscriptions</span>
            </button>
            <button
              className={`${styles.offerSwitchButton} ${offerMode === "pack" ? styles.offerSwitchButtonActive : ""}`}
              type="button"
              aria-pressed={offerMode === "pack"}
              onClick={() => setOfferMode("pack")}
            >
              <span className={styles.offerSwitchLabel}>One-time packs</span>
            </button>
          </div>

          {visiblePlanGroup ? <p className={styles.offerIntro}>{visiblePlanGroup.description}</p> : null}

          {visiblePlanGroup ? (
            <div className={styles.planGrid} data-plan-count={visiblePlanGroup.plans.length}>
              {visiblePlanGroup.plans.map((plan) => {
                const isCurrentSubscription =
                  visiblePlanGroup.key === "subscription" &&
                  account?.subscription.status === "active" &&
                  account.subscription.plan_name === plan.name;
                const planBadge = getPlanBadge(plan, visiblePlanGroup.key);
                const isRequestedPlan = requestedPlan?.plan_id === plan.plan_id;

                return (
                  <article
                    className={`${styles.planCard} ${isRequestedPlan ? styles.planCardSelected : ""}`}
                    id={`billing-plan-${plan.plan_id}`}
                    key={plan.plan_id}
                    tabIndex={isRequestedPlan ? -1 : undefined}
                  >
                    <div className={styles.planCardBody}>
                      <div>
                        <div className={styles.planHeading}>
                          <h3 className={styles.planName}>{plan.name}</h3>
                          {isRequestedPlan ? (
                            <span className={styles.planBadge}>Selected</span>
                          ) : planBadge ? (
                            <span className={styles.planBadge}>{planBadge}</span>
                          ) : null}
                        </div>
                        <p className={styles.planPrice}>{formatPrice(plan.amount_cents, plan.currency, plan.billing_interval)}</p>
                      </div>
                      <div className={styles.planMeta}>
                        <p className={chrome.subtleText}>{formatDuration(plan.quota_seconds ?? 0)} included</p>
                        {visiblePlanGroup.key === "pack" && plan.pack_expiry_days ? (
                          <p className={chrome.subtleText}>Expires in {plan.pack_expiry_days} days</p>
                        ) : null}
                      </div>
                    </div>
                    <button
                      className={isCurrentSubscription ? chrome.ghostButton : chrome.primaryButton}
                      type="button"
                      onClick={() => handleCheckout(plan.plan_id)}
                      disabled={checkoutLoading !== null || isCurrentSubscription}
                    >
                      {checkoutLoading === plan.plan_id
                        ? "Opening checkout..."
                        : isCurrentSubscription
                          ? "Current plan"
                          : visiblePlanGroup.key === "subscription"
                            ? `Choose ${plan.name}`
                            : `Buy ${plan.name}`}
                    </button>
                  </article>
                );
              })}
            </div>
          ) : null}
          <p className={chrome.subtleText}>
            Checkout shows the final currency, applicable taxes, and total before you pay.
          </p>
        </section>

        <section className={`${chrome.surface} ${styles.pageColumn} ${styles.detailsSection}`}>
          <div className={chrome.surfaceHeader}>
            <div>
              <h2 className={chrome.surfaceTitle}>Details</h2>
              <p className={chrome.surfaceText}>Only the payment details worth keeping close.</p>
            </div>
          </div>

          <div className={styles.detailsStack}>
            <details className={styles.detailDisclosure} open={activePackCount > 0}>
              <summary className={styles.detailSummary}>
                <span>Purchased packs</span>
                <span className={styles.detailCount}>{displayedPacks.length}</span>
              </summary>

              {!account || displayedPacks.length === 0 ? (
                <p className={chrome.emptyState}>No packs purchased yet.</p>
              ) : (
                <div className={chrome.list}>
                  {displayedPacks.map((pack) => (
                    <article
                      className={`${chrome.listRow} ${pack.status === "refund_pending" ? styles.packPending : ""}`}
                      key={pack.polar_order_id}
                    >
                      <div className={chrome.listPrimary}>
                        <p className={chrome.listTitle}>{pack.plan_name ?? "Pack"}</p>
                        <p className={chrome.listMeta}>
                          {pack.status === "refund_pending"
                            ? `${formatDuration(pack.remaining_seconds)} held while the refund is pending`
                            : `${formatDuration(pack.remaining_seconds)} left · Expires ${formatDate(pack.expires_at)}`}
                        </p>
                        <p className={chrome.listMeta}>
                          Used {formatDuration(pack.consumed_seconds)} / {formatDuration(pack.granted_seconds)}
                        </p>
                      </div>
                      <div className={styles.packActions}>
                        <RefundAction
                          pack={pack}
                          refundLoading={refundLoading}
                          onSelect={selectRefundTarget}
                        />
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </details>

            <details className={styles.detailDisclosure} open={(account?.orders.length ?? 0) > 0}>
              <summary className={styles.detailSummary}>
                <span>Billing history</span>
                <span className={styles.detailCount}>{account?.orders.length ?? 0}</span>
              </summary>

              {!account || account.orders.length === 0 ? (
                <p className={chrome.emptyState}>No billing events yet.</p>
              ) : (
                <div className={chrome.list}>
                  {account.orders.slice(0, 12).map((entry: BillingOrderHistoryEntry) => (
                    <article className={`${chrome.listRow} ${styles.historyRow}`} key={entry.polar_order_id}>
                      <div className={chrome.listPrimary}>
                        <p className={chrome.listTitle}>{entry.plan_name ?? entry.plan_type}</p>
                        <p className={chrome.listMeta}>{formatDate(entry.created_at)}</p>
                      </div>
                      <div className={`${chrome.listAside} ${styles.historyAside}`}>
                        <span className={getStatusTone(entry.status)}>{entry.status.replaceAll("_", " ")}</span>
                        <span>
                          Paid {formatPrice(entry.paid_amount_cents, entry.currency, null)}
                          {entry.refunded_amount_cents > 0
                            ? ` · Refunded ${formatPrice(entry.refunded_amount_cents, entry.currency, null)}`
                            : ""}
                        </span>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </details>
          </div>
        </section>
      </main>

      <Dialog.Root
        open={refundTarget !== null}
        onOpenChange={(open) => {
          if (!open) closeRefundDialog();
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className={styles.refundDialogOverlay} />
          <Dialog.Content className={styles.refundDialogContent}>
            <Dialog.Title className={styles.refundDialogTitle}>Confirm pack refund</Dialog.Title>
            <Dialog.Description className={styles.refundDialogDescription}>
              Review the amount and credit change before sending this request to the payment provider.
            </Dialog.Description>
            {refundTarget ? (
              <div className={styles.refundDialogDetails}>
                <dl>
                  <div>
                    <dt>Pack</dt>
                    <dd>{refundTarget.plan_name ?? "Pack"}</dd>
                  </div>
                  <div>
                    <dt>Refund</dt>
                    <dd>{formatPrice(refundTarget.refundable_amount_cents, refundTarget.currency, null)}</dd>
                  </div>
                  <div>
                    <dt>Video time removed</dt>
                    <dd>{formatDuration(refundTarget.remaining_seconds)}</dd>
                  </div>
                </dl>
                <p className={styles.refundDialogWarning}>
                  This prorated refund makes the remaining pack time unavailable as soon as the request starts. Used time is not refunded, and the request cannot be undone in Talven.
                </p>
                {error ? (
                  <p className={styles.refundDialogError} role="alert">
                    {error}
                  </p>
                ) : null}
              </div>
            ) : null}
            <div className={styles.refundDialogActions}>
              <Dialog.Close asChild>
                <button className={chrome.secondaryButton} type="button" disabled={refundLoading !== null}>
                  Keep pack
                </button>
              </Dialog.Close>
              <button
                className={`${chrome.primaryButton} ${styles.refundConfirmButton}`}
                type="button"
                onClick={() => void handleConfirmRefund()}
                disabled={!refundTarget || refundLoading !== null}
              >
                {refundLoading ? "Requesting refund..." : "Confirm refund"}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}

function RefundAction({
  onSelect,
  pack,
  refundLoading
}: {
  onSelect: (pack: PackBillingState) => void;
  pack: PackBillingState;
  refundLoading: string | null;
}) {
  if (pack.status === "refund_pending") return <span className={chrome.statusPillWarning}>Refund pending</span>;
  if (pack.status === "refunded") return <span className={chrome.statusPillSuccess}>Refunded</span>;
  if (!pack.is_refundable) return <span className={chrome.statusPillMuted}>Unavailable</span>;

  const refundLabel = formatPrice(pack.refundable_amount_cents, pack.currency, null);
  return (
    <button
      className={chrome.secondaryButton}
      type="button"
      onClick={() => onSelect(pack)}
      disabled={refundLoading !== null}
      aria-label={`Refund ${pack.plan_name ?? "pack"} for ${refundLabel}`}
    >
      {refundLoading === pack.polar_order_id ? "Requesting refund..." : `Refund ${refundLabel}`}
    </button>
  );
}

function BillingPageFallback() {
  const { remainingSeconds, signOut, user } = useAppShell();

  return (
    <div className={chrome.pageFrame}>
      <AppShellHeader
        active="billing"
        remainingSeconds={remainingSeconds}
        accountLabel={getAccountLabel(user)}
        onSignOut={signOut}
      />
      <main id="main-content" className={chrome.mainFrame}>
        <section className={chrome.surface} aria-busy="true">
          <h1 className={chrome.surfaceTitle}>Loading your access...</h1>
          <p className={chrome.surfaceText} role="status">Preparing your plan and billing details.</p>
        </section>
      </main>
    </div>
  );
}

export default function BillingPage() {
  return (
    <Suspense fallback={<BillingPageFallback />}>
      <BillingPageContent />
    </Suspense>
  );
}

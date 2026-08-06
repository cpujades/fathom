from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fathom.application.billing.parsing import as_int, as_str
from fathom.application.billing.webhooks import extract_provider_event_time, normalize_event_payload
from fathom.core.config import Settings
from fathom.core.constants import BILLING_DEBT_CAP_SECONDS
from fathom.core.errors import ExternalServiceError
from fathom.crud.supabase.billing import (
    apply_polar_webhook_transaction,
    claim_billing_maintenance_lease,
    get_billing_webhook_diagnostics,
    list_refund_pending_pack_orders,
    list_subscription_entitlements_for_reconciliation,
    reclaim_stale_webhook_processing,
    release_billing_maintenance_lease,
    renew_billing_maintenance_lease,
    reopen_pack_refund,
    resolve_refund_sync_operations,
    schedule_subscription_reconciliation,
)
from fathom.crud.supabase.jobs import requeue_unsettled_jobs
from fathom.services import polar

logger = logging.getLogger(__name__)

WEBHOOK_PROCESSING_STALE_MINUTES = 5
REFUND_PENDING_RECONCILIATION_GRACE_SECONDS = 60
REFUND_PENDING_RECONCILIATION_LIMIT = 100
SUBSCRIPTION_RECONCILIATION_INTERVAL = timedelta(hours=6)
SUBSCRIPTION_RECONCILIATION_RETRY_DELAY = timedelta(minutes=15)
SUBSCRIPTION_RECONCILIATION_LIMIT = 20
TERMINAL_SUBSCRIPTION_STATUSES = frozenset({"revoked", "ended", "inactive"})
BILLING_MAINTENANCE_LEASE_NAME = "billing-recovery"
BILLING_MAINTENANCE_LEASE_SECONDS = 120
BILLING_MAINTENANCE_HEARTBEAT_SECONDS = 30


async def run_billing_maintenance(
    admin_client: Any,
    *,
    settings: Settings,
) -> dict[str, int]:
    lease_token = str(uuid.uuid4())
    acquired = await claim_billing_maintenance_lease(
        admin_client,
        lease_name=BILLING_MAINTENANCE_LEASE_NAME,
        lease_token=lease_token,
        lease_seconds=BILLING_MAINTENANCE_LEASE_SECONDS,
    )
    if not acquired:
        logger.debug("billing.maintenance.lease_not_acquired")
        return {"maintenance_skipped": 1}

    maintenance_task = asyncio.create_task(_run_claimed_billing_maintenance(admin_client, settings=settings))
    heartbeat_task = asyncio.create_task(_maintain_billing_maintenance_lease(admin_client, lease_token=lease_token))
    try:
        done, _ = await asyncio.wait(
            {maintenance_task, heartbeat_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if heartbeat_task in done:
            heartbeat_error = heartbeat_task.exception()
            if heartbeat_error is not None:
                maintenance_task.cancel()
                await asyncio.gather(maintenance_task, return_exceptions=True)
                raise heartbeat_error
            raise ExternalServiceError("Billing maintenance lease heartbeat ended unexpectedly.")
        return await maintenance_task
    finally:
        if not maintenance_task.done():
            maintenance_task.cancel()
            await asyncio.gather(maintenance_task, return_exceptions=True)
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        try:
            await asyncio.shield(
                release_billing_maintenance_lease(
                    admin_client,
                    lease_name=BILLING_MAINTENANCE_LEASE_NAME,
                    lease_token=lease_token,
                )
            )
        except Exception:
            logger.warning("billing.maintenance.lease_release_failed", exc_info=True)


async def _maintain_billing_maintenance_lease(
    admin_client: Any,
    *,
    lease_token: str,
) -> None:
    while True:
        await asyncio.sleep(BILLING_MAINTENANCE_HEARTBEAT_SECONDS)
        renewed = await renew_billing_maintenance_lease(
            admin_client,
            lease_name=BILLING_MAINTENANCE_LEASE_NAME,
            lease_token=lease_token,
            lease_seconds=BILLING_MAINTENANCE_LEASE_SECONDS,
        )
        if not renewed:
            raise ExternalServiceError("Billing maintenance lease was lost.")


async def _run_claimed_billing_maintenance(
    admin_client: Any,
    *,
    settings: Settings,
) -> dict[str, int]:
    requeued_unsettled = await requeue_unsettled_jobs(admin_client)
    reclaimed_events = await reclaim_stale_webhook_processing(
        admin_client,
        stale_minutes=WEBHOOK_PROCESSING_STALE_MINUTES,
    )
    reconciled_orders = await reconcile_pending_pack_refunds(
        admin_client,
        settings=settings,
    )
    reconciled_subscriptions = await reconcile_subscription_entitlements(
        admin_client,
        settings=settings,
    )
    webhook_diagnostics = await get_billing_webhook_diagnostics(
        admin_client,
        stale_minutes=WEBHOOK_PROCESSING_STALE_MINUTES,
    )

    summary = {
        "maintenance_skipped": 0,
        "requeued_unsettled_jobs": requeued_unsettled,
        "reclaimed_webhook_events": reclaimed_events,
        "reconciled_refund_pending_orders": reconciled_orders,
        "reconciled_subscriptions": reconciled_subscriptions,
        "failed_webhook_events": int(webhook_diagnostics.get("failed_count") or 0),
        "deferred_webhook_events": int(webhook_diagnostics.get("deferred_count") or 0),
        "stale_processing_webhook_events": int(webhook_diagnostics.get("stale_processing_count") or 0),
        "deferred_unknown_order_events": int(webhook_diagnostics.get("deferred_unknown_order_count") or 0),
    }
    log_level = logging.INFO if any(summary.values()) else logging.DEBUG
    logger.log(log_level, "billing.maintenance.completed", extra=summary)
    return summary


async def reconcile_pending_pack_refunds(
    admin_client: Any,
    *,
    settings: Settings,
) -> int:
    pending_orders = await list_refund_pending_pack_orders(
        admin_client,
        updated_before=datetime.now(UTC) - timedelta(seconds=REFUND_PENDING_RECONCILIATION_GRACE_SECONDS),
        limit=REFUND_PENDING_RECONCILIATION_LIMIT,
    )

    reconciled = 0
    for order in pending_orders:
        polar_order_id = as_str(order.get("polar_order_id"))
        if not polar_order_id:
            continue

        try:
            provider_order = await polar.get_order(settings, order_id=polar_order_id)
        except Exception:
            logger.warning(
                "billing.refund_pending.reconcile_failed",
                exc_info=True,
                extra={"polar_order_id": polar_order_id},
            )
            continue

        provider_total_refunded = max(as_int(provider_order.get("refunded_amount")) or 0, 0)
        provider_status = as_str(provider_order.get("status")) or "unknown"

        if provider_total_refunded > 0:
            event_at = extract_provider_event_time(provider_order)
            if event_at is None:
                logger.warning(
                    "billing.refund_pending.reconcile_missing_provider_timestamp",
                    extra={"polar_order_id": polar_order_id},
                )
                continue
            resource_type, resource_id, payload = normalize_event_payload(
                "order.refunded",
                provider_order,
            )
            if resource_type != "order" or not resource_id:
                logger.warning(
                    "billing.refund_pending.reconcile_invalid_provider_state",
                    extra={"polar_order_id": polar_order_id},
                )
                continue
            result = await apply_polar_webhook_transaction(
                admin_client,
                event_id=_reconciliation_event_id(resource_type, resource_id, event_at),
                event_type="order.refunded",
                event_at=event_at,
                resource_type=resource_type,
                resource_id=resource_id,
                payload=payload,
                debt_cap_seconds=BILLING_DEBT_CAP_SECONDS,
            )
            if str(result.get("resolution_type") or "") in {"processed", "already_processed"}:
                await resolve_refund_sync_operations(
                    admin_client,
                    polar_order_id=polar_order_id,
                    status="succeeded",
                )
                reconciled += 1
            else:
                logger.warning(
                    "billing.refund_pending.reconcile_transaction_unresolved",
                    extra={
                        "polar_order_id": polar_order_id,
                        "resolution_type": result.get("resolution_type"),
                        "outcome": result.get("outcome"),
                    },
                )
            continue

        if provider_status == "paid":
            user_id = as_str(order.get("user_id"))
            if not user_id:
                continue
            reopen_result = await reopen_pack_refund(
                admin_client,
                user_id=user_id,
                polar_order_id=polar_order_id,
                debt_cap_seconds=BILLING_DEBT_CAP_SECONDS,
            )
            if str(reopen_result.get("resolution_type") or "") in {"reopened", "already_paid"}:
                await resolve_refund_sync_operations(
                    admin_client,
                    polar_order_id=polar_order_id,
                    status="failed",
                    failure_code="refund_not_completed",
                )
                reconciled += 1

    return reconciled


async def reconcile_subscription_entitlements(
    admin_client: Any,
    *,
    settings: Settings,
) -> int:
    now = datetime.now(UTC)
    entitlements = await list_subscription_entitlements_for_reconciliation(
        admin_client,
        due_at=now,
        limit=SUBSCRIPTION_RECONCILIATION_LIMIT,
    )

    reconciled = 0
    for entitlement in entitlements:
        user_id = as_str(entitlement.get("user_id"))
        if not user_id:
            continue

        subscription_id = as_str(entitlement.get("polar_subscription_id"))
        if not subscription_id:
            continue

        try:
            provider_subscription = await polar.get_subscription(settings, subscription_id=subscription_id)
        except Exception:
            await _schedule_subscription_reconciliation_retry(admin_client, user_id=user_id)
            logger.warning(
                "billing.subscription.reconcile_failed",
                exc_info=True,
                extra={"user_id": user_id, "polar_subscription_id": subscription_id},
            )
            continue

        event_at = extract_provider_event_time(provider_subscription)
        if event_at is None:
            await _schedule_subscription_reconciliation_retry(admin_client, user_id=user_id)
            logger.warning(
                "billing.subscription.reconcile_missing_provider_timestamp",
                extra={"user_id": user_id, "polar_subscription_id": subscription_id},
            )
            continue
        resource_type, resource_id, payload = normalize_event_payload(
            "subscription.updated",
            provider_subscription,
        )
        if resource_type != "subscription" or not resource_id:
            await _schedule_subscription_reconciliation_retry(admin_client, user_id=user_id)
            logger.warning(
                "billing.subscription.reconcile_invalid_provider_state",
                extra={"user_id": user_id, "polar_subscription_id": subscription_id},
            )
            continue
        result = await apply_polar_webhook_transaction(
            admin_client,
            event_id=_reconciliation_event_id(resource_type, resource_id, event_at),
            event_type="subscription.updated",
            event_at=event_at,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=payload,
            debt_cap_seconds=BILLING_DEBT_CAP_SECONDS,
        )
        if str(result.get("resolution_type") or "") in {"processed", "already_processed"}:
            provider_status = as_str(payload.get("status")) or "unknown"
            next_reconcile_at = (
                None
                if provider_status in TERMINAL_SUBSCRIPTION_STATUSES
                else datetime.now(UTC) + SUBSCRIPTION_RECONCILIATION_INTERVAL
            )
            await schedule_subscription_reconciliation(
                admin_client,
                user_id=user_id,
                next_reconcile_at=next_reconcile_at,
            )
            reconciled += 1
        else:
            await _schedule_subscription_reconciliation_retry(admin_client, user_id=user_id)
            logger.warning(
                "billing.subscription.reconcile_transaction_unresolved",
                extra={
                    "user_id": user_id,
                    "polar_subscription_id": subscription_id,
                    "resolution_type": result.get("resolution_type"),
                    "outcome": result.get("outcome"),
                },
            )

    return reconciled


async def _schedule_subscription_reconciliation_retry(admin_client: Any, *, user_id: str) -> None:
    await schedule_subscription_reconciliation(
        admin_client,
        user_id=user_id,
        next_reconcile_at=datetime.now(UTC) + SUBSCRIPTION_RECONCILIATION_RETRY_DELAY,
    )


def _reconciliation_event_id(resource_type: str, resource_id: str, event_at: datetime) -> str:
    return f"reconcile:{resource_type}:{resource_id}:{event_at.isoformat()}"

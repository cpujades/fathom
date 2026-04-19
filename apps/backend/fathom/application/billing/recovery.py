from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fathom.application.billing.parsing import as_int, as_str
from fathom.application.billing.state import apply_order_refund_state, sync_entitlement_snapshot
from fathom.application.billing.webhooks import apply_subscription_event
from fathom.core.config import Settings
from fathom.crud.supabase.billing import (
    list_latest_subscription_orders_for_users,
    list_refund_pending_pack_orders,
    list_subscription_entitlements_for_reconciliation,
    reclaim_stale_webhook_processing,
    transition_billing_order_status,
)
from fathom.services import polar

logger = logging.getLogger(__name__)

WEBHOOK_PROCESSING_STALE_MINUTES = 5
REFUND_PENDING_RECONCILIATION_GRACE_SECONDS = 60
REFUND_PENDING_RECONCILIATION_LIMIT = 100
SUBSCRIPTION_RECONCILIATION_GRACE_SECONDS = 300
SUBSCRIPTION_RECONCILIATION_LIMIT = 100


async def run_billing_maintenance(
    admin_client: Any,
    *,
    settings: Settings,
) -> dict[str, int]:
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

    summary = {
        "reclaimed_webhook_events": reclaimed_events,
        "reconciled_refund_pending_orders": reconciled_orders,
        "reconciled_subscriptions": reconciled_subscriptions,
    }
    logger.info("billing maintenance pass", extra=summary)
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
                "failed to reconcile refund_pending order",
                exc_info=True,
                extra={"polar_order_id": polar_order_id},
            )
            continue

        provider_total_refunded = max(as_int(provider_order.get("refunded_amount")) or 0, 0)
        provider_status = as_str(provider_order.get("status")) or "unknown"

        if provider_total_refunded > 0:
            await apply_order_refund_state(
                admin_client,
                order=order,
                settings=settings,
                provider_total_refunded=provider_total_refunded,
            )
            reconciled += 1
            continue

        if provider_status == "paid":
            reopened = await transition_billing_order_status(
                admin_client,
                order_id=str(order["id"]),
                from_status="refund_pending",
                to_status="paid",
            )
            if reopened:
                user_id = as_str(order.get("user_id"))
                if user_id:
                    await sync_entitlement_snapshot(
                        admin_client,
                        user_id=user_id,
                        settings=settings,
                    )
                reconciled += 1

    return reconciled


async def reconcile_subscription_entitlements(
    admin_client: Any,
    *,
    settings: Settings,
) -> int:
    entitlements = await list_subscription_entitlements_for_reconciliation(
        admin_client,
        updated_before=datetime.now(UTC) - timedelta(seconds=SUBSCRIPTION_RECONCILIATION_GRACE_SECONDS),
        limit=SUBSCRIPTION_RECONCILIATION_LIMIT,
    )
    latest_orders_by_user = await list_latest_subscription_orders_for_users(
        admin_client,
        user_ids={str(entitlement.get("user_id") or "") for entitlement in entitlements if entitlement.get("user_id")},
    )

    reconciled = 0
    for entitlement in entitlements:
        user_id = as_str(entitlement.get("user_id"))
        if not user_id:
            continue

        latest_order = latest_orders_by_user.get(user_id)
        subscription_id = as_str(latest_order.get("polar_subscription_id")) if latest_order else None
        if not subscription_id:
            continue

        try:
            provider_subscription = await polar.get_subscription(settings, subscription_id=subscription_id)
        except Exception:
            logger.warning(
                "failed to reconcile subscription entitlement",
                exc_info=True,
                extra={"user_id": user_id, "polar_subscription_id": subscription_id},
            )
            continue

        await apply_subscription_event(
            admin_client,
            provider_subscription,
            settings,
            event_type="subscription.reconciled",
        )
        reconciled += 1

    return reconciled

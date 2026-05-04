from __future__ import annotations

import logging

from fathom.api.deps.auth import AuthContext
from fathom.application.billing.parsing import as_str, is_definitive_duplicate_refund_error
from fathom.application.billing.state import sync_entitlement_snapshot
from fathom.core.config import Settings
from fathom.core.errors import InvalidRequestError
from fathom.crud.supabase.billing import (
    fetch_billing_order_for_user,
    fetch_credit_lot_by_source,
    transition_billing_order_status,
)
from fathom.schemas.billing import PackRefundResponse
from fathom.services import polar
from fathom.services.supabase import create_supabase_admin_client

logger = logging.getLogger(__name__)


async def request_pack_refund(
    *,
    polar_order_id: str,
    auth: AuthContext,
    settings: Settings,
) -> PackRefundResponse:
    admin_client = await create_supabase_admin_client(settings)
    order = await fetch_billing_order_for_user(
        admin_client,
        user_id=auth.user_id,
        polar_order_id=polar_order_id,
    )
    if not order:
        raise InvalidRequestError("Pack order not found.")

    if order.get("plan_type") != "pack":
        raise InvalidRequestError("Only pack orders can be refunded from this endpoint.")

    status = as_str(order.get("status")) or "paid"
    if status == "refund_pending":
        raise InvalidRequestError("Refund is already in progress for this order.")
    if status == "refunded":
        raise InvalidRequestError("This order has already been refunded.")

    lot = await fetch_credit_lot_by_source(
        admin_client,
        lot_type="pack_order",
        source_key=polar_order_id,
    )
    if not lot:
        raise InvalidRequestError("Pack lot not found for this order.")

    granted_seconds = int(lot.get("granted_seconds") or 0)
    consumed_seconds = int(lot.get("consumed_seconds") or 0)
    revoked_seconds = int(lot.get("revoked_seconds") or 0)
    remaining_seconds = max(granted_seconds - consumed_seconds - revoked_seconds, 0)
    paid_amount_cents = int(order.get("paid_amount_cents") or 0)

    if granted_seconds <= 0 or paid_amount_cents <= 0:
        raise InvalidRequestError("Order is not refundable.")
    if remaining_seconds <= 0:
        raise InvalidRequestError("No refundable amount remaining for this pack order.")

    refundable_amount_cents = (paid_amount_cents * remaining_seconds) // granted_seconds
    if refundable_amount_cents <= 0:
        raise InvalidRequestError("No refundable amount remaining for this pack order.")

    transitioned = await transition_billing_order_status(
        admin_client,
        order_id=str(order["id"]),
        from_status="paid",
        to_status="refund_pending",
    )
    if not transitioned:
        refreshed = await fetch_billing_order_for_user(
            admin_client,
            user_id=auth.user_id,
            polar_order_id=polar_order_id,
        )
        refreshed_status = as_str(refreshed.get("status")) if refreshed else None
        if refreshed_status == "refunded":
            raise InvalidRequestError("This order has already been refunded.")
        if refreshed_status == "refund_pending":
            raise InvalidRequestError("Refund is already in progress for this order.")
        raise InvalidRequestError("Order is not refundable at this time.")

    await sync_entitlement_snapshot(
        admin_client,
        user_id=auth.user_id,
        settings=settings,
    )

    try:
        refund = await polar.create_order_refund(
            settings,
            polar_order_id=polar_order_id,
            amount_cents=refundable_amount_cents,
        )
    except polar.PolarInvalidRequestError as exc:
        if exc.http_status == 409 or is_definitive_duplicate_refund_error(exc.detail):
            logger.warning(
                "billing.refund.duplicate_or_conflict",
                extra={"polar_order_id": polar_order_id, "http_status": exc.http_status},
            )
            raise InvalidRequestError(
                "Refund request already exists or may have already been processed. "
                "Please wait for webhook confirmation."
            ) from exc

        await transition_billing_order_status(
            admin_client,
            order_id=str(order["id"]),
            from_status="refund_pending",
            to_status="paid",
        )
        await sync_entitlement_snapshot(
            admin_client,
            user_id=auth.user_id,
            settings=settings,
        )
        raise
    except Exception:
        logger.exception("billing.refund.outcome_unknown", extra={"polar_order_id": polar_order_id})
        raise

    refund_id = as_str(refund.get("id"))
    return PackRefundResponse(
        polar_order_id=polar_order_id,
        refund_id=refund_id,
        requested_amount_cents=refundable_amount_cents,
        remaining_seconds_before_refund=remaining_seconds,
        status="pending_webhook_confirmation",
    )

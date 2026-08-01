from __future__ import annotations

import logging

from fathom.api.deps.auth import AuthContext
from fathom.application.billing.parsing import as_str, is_definitive_duplicate_refund_error
from fathom.core.config import Settings
from fathom.core.errors import ExternalServiceError, InvalidRequestError
from fathom.crud.supabase.billing import (
    begin_pack_refund,
    reopen_pack_refund,
)
from fathom.schemas.billing import PackRefundResponse
from fathom.services import polar
from fathom.services.supabase import create_supabase_admin_client, managed_supabase_client
from supabase import AsyncClient

logger = logging.getLogger(__name__)


async def request_pack_refund(
    *,
    polar_order_id: str,
    auth: AuthContext,
    settings: Settings,
) -> PackRefundResponse:
    async with managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client:
        return await _request_pack_refund(
            polar_order_id=polar_order_id,
            auth=auth,
            settings=settings,
            admin_client=admin_client,
        )


async def _request_pack_refund(
    *,
    polar_order_id: str,
    auth: AuthContext,
    settings: Settings,
    admin_client: AsyncClient,
) -> PackRefundResponse:
    resolution = await begin_pack_refund(
        admin_client,
        user_id=auth.user_id,
        polar_order_id=polar_order_id,
        debt_cap_seconds=settings.billing_debt_cap_seconds,
    )
    resolution_type = str(resolution.get("resolution_type") or "")
    if resolution_type == "not_found":
        raise InvalidRequestError("Pack order not found.")
    if resolution_type == "not_pack":
        raise InvalidRequestError("Only pack orders can be refunded from this endpoint.")
    if resolution_type == "already_pending":
        raise InvalidRequestError("Refund is already in progress for this order.")
    if resolution_type == "already_refunded":
        raise InvalidRequestError("This order has already been refunded.")
    if resolution_type == "lot_not_found":
        raise InvalidRequestError("Pack lot not found for this order.")
    if resolution_type == "not_refundable":
        raise InvalidRequestError("Order is not refundable.")
    if resolution_type == "nothing_remaining":
        raise InvalidRequestError("No refundable amount remaining for this pack order.")
    if resolution_type != "started":
        raise ExternalServiceError("Pack refund could not be started.")

    refundable_amount_cents = int(resolution.get("refundable_amount_cents") or 0)
    remaining_seconds = int(resolution.get("remaining_seconds_before_refund") or 0)
    if refundable_amount_cents <= 0 or remaining_seconds <= 0:
        raise ExternalServiceError("Pack refund returned an invalid authoritative amount.")

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

        await reopen_pack_refund(
            admin_client,
            user_id=auth.user_id,
            polar_order_id=polar_order_id,
            debt_cap_seconds=settings.billing_debt_cap_seconds,
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

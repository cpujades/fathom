from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from fathom.api.deps.auth import AuthContext
from fathom.core.config import Settings
from fathom.core.errors import InvalidRequestError
from fathom.core.logging import log_context
from fathom.crud.supabase.billing import (
    expire_active_subscription_lots,
    fetch_billing_order_by_polar_id,
    fetch_billing_order_for_user,
    fetch_credit_lot_by_id,
    fetch_credit_lot_by_source,
    fetch_entitlement,
    fetch_plan_by_id,
    fetch_plan_by_product_id,
    mark_webhook_event_failed,
    mark_webhook_event_processed,
    record_webhook_event_received,
    remaining_seconds_from_lot,
    revoke_remaining_credit_lot,
    summarize_credit_lots,
    update_billing_order,
    update_credit_lot,
    update_entitlement_debt,
    update_entitlement_snapshot,
    upsert_billing_order,
    upsert_credit_lot,
    upsert_polar_customer,
    upsert_subscription_entitlement_state,
)
from fathom.schemas.billing import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CustomerPortalSessionResponse,
    PackRefundResponse,
)
from fathom.services import polar
from fathom.services.supabase import create_supabase_admin_client

logger = logging.getLogger(__name__)


def _as_str(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    if isinstance(value, int):
        return datetime.fromtimestamp(value, UTC)
    return None


def _extract_event_fields(event: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    event_id = _as_str(event.get("id"))
    event_type = _as_str(event.get("type"))
    data = event.get("data")

    if not event_id or not event_type or not isinstance(data, dict):
        raise InvalidRequestError("Invalid Polar webhook payload.")

    return event_id, event_type, data


async def _sync_entitlement_snapshot(
    admin_client: Any,
    *,
    user_id: str,
    settings: Settings,
    debt_seconds: int | None = None,
) -> None:
    entitlement = await fetch_entitlement(admin_client, user_id)
    effective_debt = int(entitlement.get("debt_seconds") or 0) if entitlement else 0
    if debt_seconds is not None:
        effective_debt = max(debt_seconds, 0)

    now = datetime.now(UTC)
    subscription_remaining, pack_remaining, next_pack_expiry = await summarize_credit_lots(
        admin_client,
        user_id=user_id,
        now=now,
    )
    is_blocked = effective_debt >= settings.billing_debt_cap_seconds

    await update_entitlement_snapshot(
        admin_client,
        user_id=user_id,
        subscription_available_seconds=subscription_remaining,
        pack_available_seconds=pack_remaining,
        pack_expires_at=next_pack_expiry,
        debt_seconds=effective_debt,
        is_blocked=is_blocked,
        last_balance_sync_at=now,
    )


async def _apply_debt_paydown_for_lot(
    admin_client: Any,
    *,
    user_id: str,
    lot_id: str,
    settings: Settings,
) -> int:
    entitlement = await fetch_entitlement(admin_client, user_id)
    debt_seconds = int(entitlement.get("debt_seconds") or 0) if entitlement else 0
    if debt_seconds <= 0:
        return 0

    lot = await fetch_credit_lot_by_id(admin_client, lot_id)
    if not lot:
        return debt_seconds

    available = remaining_seconds_from_lot(lot)
    if available <= 0:
        return debt_seconds

    paydown = min(available, debt_seconds)
    if paydown <= 0:
        return debt_seconds

    current_consumed = int(lot.get("consumed_seconds") or 0)
    await update_credit_lot(
        admin_client,
        lot_id=lot_id,
        values={"consumed_seconds": current_consumed + paydown},
    )

    new_debt = max(debt_seconds - paydown, 0)
    await update_entitlement_debt(
        admin_client,
        user_id=user_id,
        debt_seconds=new_debt,
        is_blocked=new_debt >= settings.billing_debt_cap_seconds,
    )
    return new_debt


async def create_checkout_session(
    request: CheckoutSessionRequest,
    auth: AuthContext,
    settings: Settings,
) -> CheckoutSessionResponse:
    plan_id = str(request.plan_id)
    with log_context(user_id=auth.user_id, plan_id=plan_id):
        admin_client = await create_supabase_admin_client(settings)
        plan = await fetch_plan_by_id(admin_client, plan_id)
        if not plan.get("is_active"):
            raise InvalidRequestError("Plan is not active.")

        plan_type = str(plan["plan_type"])
        product_id = _as_str(plan.get("polar_product_id"))
        if plan_type not in {"subscription", "pack"}:
            raise InvalidRequestError("Plan type is invalid.")
        if plan_type == "subscription" and product_id == "internal_free":
            raise InvalidRequestError("Free plan does not require checkout.")
        if not product_id:
            raise InvalidRequestError("Plan is missing a Polar product id.")

        await upsert_polar_customer(
            admin_client,
            user_id=auth.user_id,
            external_customer_id=auth.user_id,
        )

        checkout_url = await polar.create_checkout_session(
            settings,
            product_id=product_id,
            external_customer_id=auth.user_id,
            metadata={
                "user_id": auth.user_id,
                "plan_id": plan_id,
                "plan_code": str(plan.get("plan_code") or ""),
                "version": str(plan.get("version") or 1),
                "plan_type": plan_type,
            },
        )

        logger.info("polar checkout session created", extra={"user_id": auth.user_id, "plan_id": plan_id})
        return CheckoutSessionResponse(checkout_url=checkout_url)


async def create_portal_session(auth: AuthContext, settings: Settings) -> CustomerPortalSessionResponse:
    admin_client = await create_supabase_admin_client(settings)
    await upsert_polar_customer(
        admin_client,
        user_id=auth.user_id,
        external_customer_id=auth.user_id,
    )

    portal_url = await polar.create_customer_portal_session(
        settings,
        external_customer_id=auth.user_id,
    )

    return CustomerPortalSessionResponse(portal_url=portal_url)


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

    status = _as_str(order.get("status")) or "paid"
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
    remaining_seconds = remaining_seconds_from_lot(lot)
    paid_amount_cents = int(order.get("paid_amount_cents") or 0)

    if granted_seconds <= 0 or paid_amount_cents <= 0:
        raise InvalidRequestError("Order is not refundable.")
    if remaining_seconds <= 0:
        raise InvalidRequestError("No refundable amount remaining for this pack order.")

    refundable_amount_cents = (paid_amount_cents * remaining_seconds) // granted_seconds
    if refundable_amount_cents <= 0:
        raise InvalidRequestError("No refundable amount remaining for this pack order.")

    await update_billing_order(
        admin_client,
        order_id=str(order["id"]),
        values={"status": "refund_pending"},
    )
    try:
        refund = await polar.create_order_refund(
            settings,
            polar_order_id=polar_order_id,
            amount_cents=refundable_amount_cents,
        )
    except Exception:
        await update_billing_order(
            admin_client,
            order_id=str(order["id"]),
            values={"status": "paid"},
        )
        raise

    refund_id = _as_str(refund.get("id"))
    return PackRefundResponse(
        polar_order_id=polar_order_id,
        refund_id=refund_id,
        requested_amount_cents=refundable_amount_cents,
        remaining_seconds_before_refund=remaining_seconds,
        status="pending_webhook_confirmation",
    )


async def handle_polar_webhook(payload: bytes, headers: Mapping[str, str], settings: Settings) -> None:
    event = polar.verify_and_parse_webhook(payload, headers, settings)
    event_id, event_type, data = _extract_event_fields(event)

    admin_client = await create_supabase_admin_client(settings)
    inserted = await record_webhook_event_received(
        admin_client,
        event_id=event_id,
        provider="polar",
        event_type=event_type,
        payload=event,
    )
    if not inserted:
        logger.info("polar webhook duplicate ignored", extra={"event_id": event_id, "event_type": event_type})
        return

    try:
        if event_type == "order.paid":
            await _handle_order_paid(admin_client, data, settings)
        elif event_type == "order.refunded":
            await _handle_order_refunded(admin_client, data, settings)
        elif event_type in {"subscription.updated", "subscription.revoked"}:
            await _handle_subscription_event(admin_client, data, settings)
        elif event_type in {"customer.created", "customer.state_changed"}:
            await _handle_customer_event(admin_client, data)
        else:
            logger.info("polar webhook ignored", extra={"event_type": event_type})

        await mark_webhook_event_processed(admin_client, event_id)
    except Exception as exc:
        await mark_webhook_event_failed(admin_client, event_id, str(exc))
        raise


async def _handle_customer_event(admin_client: Any, data: dict[str, Any]) -> None:
    external_customer_id = _as_str(data.get("external_id"))
    if not external_customer_id:
        return

    billing_address = data.get("billing_address")
    country = None
    if isinstance(billing_address, dict):
        country = _as_str(billing_address.get("country"))

    await upsert_polar_customer(
        admin_client,
        user_id=external_customer_id,
        external_customer_id=external_customer_id,
        polar_customer_id=_as_str(data.get("id")),
        email=_as_str(data.get("email")),
        country=country,
    )


async def _handle_order_paid(admin_client: Any, order: dict[str, Any], settings: Settings) -> None:
    polar_order_id = _as_str(order.get("id"))
    if not polar_order_id:
        raise InvalidRequestError("Polar order payload is missing id.")

    user_id = _as_str(order.get("customer_external_id"))
    if not user_id:
        metadata = order.get("metadata")
        if isinstance(metadata, dict):
            user_id = _as_str(metadata.get("user_id"))
    if not user_id:
        raise InvalidRequestError("Polar order payload is missing external customer id.")

    product_id = _as_str(order.get("product_id"))
    if not product_id:
        raise InvalidRequestError("Polar order payload is missing product mapping.")

    plan = await fetch_plan_by_product_id(admin_client, product_id)
    plan_type = str(plan["plan_type"])
    paid_amount_cents = int(_as_int(order.get("amount")) or 0)
    currency = _as_str(order.get("currency")) or str(plan.get("currency") or "usd")
    subscription_id = _as_str(order.get("subscription_id"))

    _order_row = await upsert_billing_order(
        admin_client,
        polar_order_id=polar_order_id,
        user_id=user_id,
        plan_id=str(plan["id"]),
        plan_type=plan_type,
        polar_product_id=product_id,
        polar_subscription_id=subscription_id,
        currency=currency,
        paid_amount_cents=paid_amount_cents,
        status="paid",
    )

    await upsert_polar_customer(
        admin_client,
        user_id=user_id,
        external_customer_id=user_id,
        polar_customer_id=_as_str(order.get("customer_id")),
        email=_as_str(order.get("customer", {}).get("email")) if isinstance(order.get("customer"), dict) else None,
    )

    if plan_type == "pack":
        granted_seconds = int(plan.get("quota_seconds") or 0)
        pack_expiry_days = int(plan.get("pack_expiry_days") or 0)
        pack_expires_at = datetime.now(UTC) + timedelta(days=pack_expiry_days)

        lot = await upsert_credit_lot(
            admin_client,
            user_id=user_id,
            plan_id=str(plan["id"]),
            lot_type="pack_order",
            source_key=polar_order_id,
            granted_seconds=granted_seconds,
            pack_expires_at=pack_expires_at,
            status="active",
        )

        debt_after_paydown = await _apply_debt_paydown_for_lot(
            admin_client,
            user_id=user_id,
            lot_id=str(lot["id"]),
            settings=settings,
        )
        await _sync_entitlement_snapshot(
            admin_client,
            user_id=user_id,
            settings=settings,
            debt_seconds=debt_after_paydown,
        )
        return

    # Subscription orders are tracked for payment history. Entitlements are reconciled from subscription events.
    await _sync_entitlement_snapshot(
        admin_client,
        user_id=user_id,
        settings=settings,
    )

    logger.info("polar order tracked")


async def _handle_order_refunded(admin_client: Any, refund: dict[str, Any], settings: Settings) -> None:
    polar_order_id = _as_str(refund.get("order_id"))
    if not polar_order_id:
        raise InvalidRequestError("Polar refund payload is missing order id.")

    order = await fetch_billing_order_by_polar_id(admin_client, polar_order_id)
    if not order:
        logger.info("polar refund ignored: order not tracked", extra={"polar_order_id": polar_order_id})
        return

    refund_amount_cents = int(_as_int(refund.get("amount")) or 0)
    await update_billing_order(
        admin_client,
        order_id=str(order["id"]),
        values={
            "status": "refunded",
            "refunded_amount_cents": refund_amount_cents,
        },
    )

    if order.get("plan_type") == "pack":
        lot = await fetch_credit_lot_by_source(
            admin_client,
            lot_type="pack_order",
            source_key=polar_order_id,
        )
        if lot:
            await revoke_remaining_credit_lot(admin_client, lot_id=str(lot["id"]))

    user_id = _as_str(order.get("user_id"))
    if user_id:
        await _sync_entitlement_snapshot(
            admin_client,
            user_id=user_id,
            settings=settings,
        )


async def _handle_subscription_event(admin_client: Any, subscription: dict[str, Any], settings: Settings) -> None:
    user_id = _as_str(subscription.get("customer_external_id"))
    if not user_id:
        raise InvalidRequestError("Polar subscription payload is missing external customer id.")

    product_id = _as_str(subscription.get("product_id"))
    if not product_id:
        raise InvalidRequestError("Polar subscription payload is missing product mapping.")

    plan = await fetch_plan_by_product_id(admin_client, product_id)
    existing = await fetch_entitlement(admin_client, user_id)

    status = _as_str(subscription.get("status")) or "unknown"
    period_start = _parse_dt(subscription.get("current_period_start"))
    period_end = _parse_dt(subscription.get("current_period_end"))
    subscription_id = _as_str(subscription.get("id")) or _as_str(subscription.get("subscription_id"))

    quota_seconds = int(plan.get("quota_seconds") or 0)
    rollover_cap = int(plan.get("rollover_cap_seconds") or 0)
    existing_subscription_remaining = int(existing.get("subscription_available_seconds") or 0) if existing else 0
    rollover_seconds = min(existing_subscription_remaining, rollover_cap)

    debt_after_paydown: int | None = None

    if status in {"revoked", "canceled", "cancelled", "ended", "inactive"}:
        await expire_active_subscription_lots(admin_client, user_id=user_id)
    elif period_start and period_end:
        source_key = f"{subscription_id or 'subscription'}:{period_start.isoformat()}"
        await expire_active_subscription_lots(admin_client, user_id=user_id)

        lot = await upsert_credit_lot(
            admin_client,
            user_id=user_id,
            plan_id=str(plan["id"]),
            lot_type="subscription_cycle",
            source_key=source_key,
            granted_seconds=quota_seconds + rollover_seconds,
            pack_expires_at=period_end,
            status="active",
        )
        debt_after_paydown = await _apply_debt_paydown_for_lot(
            admin_client,
            user_id=user_id,
            lot_id=str(lot["id"]),
            settings=settings,
        )

    await upsert_subscription_entitlement_state(
        admin_client,
        user_id=user_id,
        subscription_plan_id=str(plan["id"]),
        subscription_status=status,
        period_start=period_start,
        period_end=period_end,
        subscription_cycle_grant_seconds=quota_seconds,
        subscription_rollover_seconds=rollover_seconds,
        subscription_available_seconds=max(quota_seconds + rollover_seconds, 0),
    )

    await upsert_polar_customer(
        admin_client,
        user_id=user_id,
        external_customer_id=user_id,
        polar_customer_id=_as_str(subscription.get("customer_id")),
    )

    await _sync_entitlement_snapshot(
        admin_client,
        user_id=user_id,
        settings=settings,
        debt_seconds=debt_after_paydown,
    )

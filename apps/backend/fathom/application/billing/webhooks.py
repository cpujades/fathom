from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from fathom.application.billing.parsing import (
    FREE_TIER_PRODUCT_ID,
    as_str,
    extract_amount_cents,
    extract_event_fields,
    parse_dt,
)
from fathom.application.billing.state import (
    apply_debt_paydown_for_lot,
    apply_order_refund_state,
    sync_entitlement_snapshot,
)
from fathom.core.config import Settings
from fathom.core.errors import ExternalServiceError, InvalidRequestError
from fathom.crud.supabase.billing import (
    claim_webhook_event_for_processing,
    expire_active_subscription_lots,
    fetch_billing_order_by_polar_id,
    fetch_credit_lot_by_source,
    fetch_entitlement,
    fetch_plan_by_product_id,
    mark_webhook_event_failed,
    mark_webhook_event_processed,
    record_webhook_event_received,
    summarize_credit_lots,
    update_billing_order,
    upsert_billing_order,
    upsert_credit_lot,
    upsert_polar_customer,
    upsert_subscription_entitlement_state,
)
from fathom.services import polar
from fathom.services.supabase import create_supabase_admin_client

logger = logging.getLogger(__name__)


async def handle_polar_webhook(payload: bytes, headers: Mapping[str, str], settings: Settings) -> None:
    try:
        event = polar.verify_and_parse_webhook(payload, headers, settings)
    except InvalidRequestError as exc:
        logger.warning(
            "polar webhook rejected before processing",
            extra={
                "has_webhook_id": bool(headers.get("webhook-id") or headers.get("svix-id")),
                "has_webhook_timestamp": bool(headers.get("webhook-timestamp") or headers.get("svix-timestamp")),
                "has_webhook_signature": bool(headers.get("webhook-signature") or headers.get("svix-signature")),
                "reason": exc.detail,
            },
        )
        raise

    event_id, event_type, data = extract_event_fields(event, headers)
    admin_client = await create_supabase_admin_client(settings)
    inserted = await record_webhook_event_received(
        admin_client,
        event_id=event_id,
        provider="polar",
        event_type=event_type,
        payload=event,
    )
    claimed = await claim_webhook_event_for_processing(admin_client, event_id=event_id)
    if not claimed:
        logger.info("polar webhook duplicate ignored", extra={"event_id": event_id, "event_type": event_type})
        return
    if not inserted:
        logger.info("polar webhook retry claimed", extra={"event_id": event_id, "event_type": event_type})

    try:
        if event_type == "order.paid":
            await _handle_order_paid(admin_client, data, settings)
        elif event_type == "order.refunded":
            await _handle_order_refunded(admin_client, data, settings)
        elif event_type in {
            "subscription.created",
            "subscription.active",
            "subscription.uncanceled",
            "subscription.canceled",
            "subscription.past_due",
            "subscription.updated",
            "subscription.revoked",
        }:
            await apply_subscription_event(admin_client, data, settings, event_type=event_type)
        elif event_type in {"customer.created", "customer.state_changed"}:
            await _handle_customer_event(admin_client, data)
        else:
            logger.info("polar webhook ignored", extra={"event_type": event_type})

        await mark_webhook_event_processed(admin_client, event_id)
    except Exception as exc:
        await mark_webhook_event_failed(admin_client, event_id, str(exc))
        raise


async def _handle_customer_event(admin_client: Any, data: dict[str, Any]) -> None:
    external_customer_id = as_str(data.get("external_id"))
    if not external_customer_id:
        return

    billing_address = data.get("billing_address")
    country = None
    if isinstance(billing_address, dict):
        country = as_str(billing_address.get("country"))

    await upsert_polar_customer(
        admin_client,
        user_id=external_customer_id,
        external_customer_id=external_customer_id,
        polar_customer_id=as_str(data.get("id")),
        email=as_str(data.get("email")),
        country=country,
    )


async def _handle_order_paid(admin_client: Any, order: dict[str, Any], settings: Settings) -> None:
    polar_order_id = as_str(order.get("id"))
    if not polar_order_id:
        raise InvalidRequestError("Polar order payload is missing id.")

    user_id = as_str(order.get("customer_external_id"))
    if not user_id:
        customer = order.get("customer")
        if isinstance(customer, dict):
            user_id = as_str(customer.get("external_id"))
    if not user_id:
        metadata = order.get("metadata")
        if isinstance(metadata, dict):
            user_id = as_str(metadata.get("user_id"))
    if not user_id:
        raise InvalidRequestError("Polar order payload is missing external customer id.")

    product_id = as_str(order.get("product_id"))
    if not product_id:
        product = order.get("product")
        if isinstance(product, dict):
            product_id = as_str(product.get("id"))
    if not product_id:
        raise InvalidRequestError("Polar order payload is missing product mapping.")

    plan = await fetch_plan_by_product_id(admin_client, product_id)
    plan_type = str(plan["plan_type"])
    paid_amount_cents = extract_amount_cents(
        order,
        candidates=("total_amount", "net_amount", "amount"),
    )
    currency = as_str(order.get("currency")) or str(plan.get("currency") or "usd")
    subscription_id = as_str(order.get("subscription_id"))
    existing_order = await fetch_billing_order_by_polar_id(admin_client, polar_order_id)
    preserved_status = _preserve_paid_event_status(existing_order)

    if existing_order:
        await update_billing_order(
            admin_client,
            order_id=str(existing_order["id"]),
            values={
                "user_id": user_id,
                "plan_id": str(plan["id"]),
                "plan_type": plan_type,
                "polar_product_id": product_id,
                "polar_subscription_id": subscription_id,
                "currency": currency.lower(),
                "paid_amount_cents": paid_amount_cents,
                "status": preserved_status or "paid",
            },
        )
    else:
        await upsert_billing_order(
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
        polar_customer_id=as_str(order.get("customer_id")),
        email=as_str(order.get("customer", {}).get("email")) if isinstance(order.get("customer"), dict) else None,
    )

    if preserved_status:
        await sync_entitlement_snapshot(
            admin_client,
            user_id=user_id,
            settings=settings,
        )
        logger.info(
            "preserved billing order status while applying order.paid",
            extra={"polar_order_id": polar_order_id, "status": preserved_status},
        )
        return

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

        debt_after_paydown = await apply_debt_paydown_for_lot(
            admin_client,
            user_id=user_id,
            lot_id=str(lot["id"]),
            settings=settings,
        )
        await sync_entitlement_snapshot(
            admin_client,
            user_id=user_id,
            settings=settings,
            debt_seconds=debt_after_paydown,
        )
        return

    await sync_entitlement_snapshot(
        admin_client,
        user_id=user_id,
        settings=settings,
    )
    logger.info("polar order tracked")


def _preserve_paid_event_status(order: dict[str, Any] | None) -> str | None:
    if not order:
        return None

    current_status = as_str(order.get("status"))
    if current_status in {"refund_pending", "refunded"}:
        return current_status
    return None


async def _handle_order_refunded(admin_client: Any, refund: dict[str, Any], settings: Settings) -> None:
    candidate_order_ids: list[str] = []
    order_id = as_str(refund.get("order_id"))
    if order_id:
        candidate_order_ids.append(order_id)
    refund_id = as_str(refund.get("id"))
    if refund_id:
        candidate_order_ids.append(refund_id)
    nested_order = refund.get("order")
    if isinstance(nested_order, dict):
        nested_order_id = as_str(nested_order.get("id"))
        if nested_order_id:
            candidate_order_ids.append(nested_order_id)

    if not candidate_order_ids:
        raise InvalidRequestError("Polar refund payload is missing order id.")

    order: dict[str, Any] | None = None
    for candidate in candidate_order_ids:
        found = await fetch_billing_order_by_polar_id(admin_client, candidate)
        if found:
            order = found
            break

    if not order:
        raise ExternalServiceError(f"Polar refund payload references unknown order ids: {candidate_order_ids}")

    provider_total_refunded = None
    for key in ("refunded_amount", "total_refunded_amount"):
        value = refund.get(key)
        if isinstance(value, int):
            provider_total_refunded = max(value, 0)
            break
        if isinstance(value, str):
            try:
                provider_total_refunded = max(int(value), 0)
                break
            except ValueError:
                continue

    await apply_order_refund_state(
        admin_client,
        order=order,
        settings=settings,
        provider_total_refunded=provider_total_refunded,
        refund_delta_cents=extract_amount_cents(refund, candidates=("refund_amount", "amount")),
    )


async def apply_subscription_event(
    admin_client: Any,
    subscription: dict[str, Any],
    settings: Settings,
    *,
    event_type: str,
) -> None:
    user_id = as_str(subscription.get("customer_external_id"))
    if not user_id:
        customer = subscription.get("customer")
        if isinstance(customer, dict):
            user_id = as_str(customer.get("external_id"))
    if not user_id:
        metadata = subscription.get("metadata")
        if isinstance(metadata, dict):
            user_id = as_str(metadata.get("user_id"))
    if not user_id:
        raise InvalidRequestError("Polar subscription payload is missing external customer id.")

    product_id = as_str(subscription.get("product_id"))
    if not product_id:
        product = subscription.get("product")
        if isinstance(product, dict):
            product_id = as_str(product.get("id"))
    if not product_id:
        raise InvalidRequestError("Polar subscription payload is missing product mapping.")

    plan = await fetch_plan_by_product_id(admin_client, product_id)
    existing = await fetch_entitlement(admin_client, user_id)
    existing_plan_id = as_str(existing.get("subscription_plan_id")) if existing else None
    same_subscription_plan = existing_plan_id == str(plan["id"])

    status = as_str(subscription.get("status")) or "unknown"
    period_start = parse_dt(subscription.get("current_period_start"))
    period_end = parse_dt(subscription.get("current_period_end"))
    subscription_id = as_str(subscription.get("id")) or as_str(subscription.get("subscription_id"))

    quota_seconds = int(plan.get("quota_seconds") or 0)
    rollover_cap = int(plan.get("rollover_cap_seconds") or 0)
    rollover_seconds = int(existing.get("subscription_rollover_seconds") or 0) if existing else 0

    debt_after_paydown: int | None = None

    if event_type == "subscription.revoked" or status in {"revoked", "ended", "inactive"}:
        rollover_seconds = 0
        await expire_active_subscription_lots(admin_client, user_id=user_id)
    elif period_start and period_end:
        subscription_key = subscription_id or f"user:{user_id}"
        source_key = f"{subscription_key}:{period_start.isoformat()}"
        existing_cycle_lot = await fetch_credit_lot_by_source(
            admin_client,
            lot_type="subscription_cycle",
            source_key=source_key,
        )
        if existing_cycle_lot:
            granted_seconds = int(existing_cycle_lot.get("granted_seconds") or 0)
            rollover_seconds = max(granted_seconds - quota_seconds, 0)
        else:
            if same_subscription_plan and product_id != FREE_TIER_PRODUCT_ID:
                current_subscription_remaining, _, _ = await summarize_credit_lots(
                    admin_client,
                    user_id=user_id,
                    now=datetime.now(UTC),
                )
                rollover_seconds = min(current_subscription_remaining, rollover_cap)
            else:
                rollover_seconds = 0
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
            debt_after_paydown = await apply_debt_paydown_for_lot(
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
        polar_customer_id=as_str(subscription.get("customer_id")),
    )

    await sync_entitlement_snapshot(
        admin_client,
        user_id=user_id,
        settings=settings,
        debt_seconds=debt_after_paydown,
    )

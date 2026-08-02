from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from fathom.application.billing.parsing import as_str, extract_amount_cents, extract_event_fields, parse_dt
from fathom.core.config import Settings
from fathom.core.errors import ExternalServiceError, InvalidRequestError
from fathom.core.logging import log_context
from fathom.crud.supabase.billing import apply_polar_webhook_transaction
from fathom.services import polar
from fathom.services.supabase import create_supabase_admin_client, managed_supabase_client

logger = logging.getLogger(__name__)


async def handle_polar_webhook(payload: bytes, headers: Mapping[str, str], settings: Settings) -> None:
    try:
        event = polar.verify_and_parse_webhook(payload, headers, settings)
    except InvalidRequestError as exc:
        logger.warning(
            "billing.webhook.rejected",
            extra={
                "has_webhook_id": bool(headers.get("webhook-id") or headers.get("svix-id")),
                "has_webhook_timestamp": bool(headers.get("webhook-timestamp") or headers.get("svix-timestamp")),
                "has_webhook_signature": bool(headers.get("webhook-signature") or headers.get("svix-signature")),
                "reason": exc.detail,
            },
        )
        raise

    event_id, event_type, data = extract_event_fields(event, headers)
    with log_context(provider_event_id=event_id, provider_event_type=event_type):
        async with managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client:
            event_at = extract_event_time(event, data, headers)
            resource_type, resource_id, normalized_payload = normalize_event_payload(event_type, data)
            result = await apply_polar_webhook_transaction(
                admin_client,
                event_id=event_id,
                event_type=event_type,
                event_at=event_at,
                resource_type=resource_type,
                resource_id=resource_id,
                payload=normalized_payload,
                debt_cap_seconds=settings.billing_debt_cap_seconds,
            )
            resolution_type = str(result.get("resolution_type") or "")
            outcome = str(result.get("outcome") or "")
            if resolution_type == "failed":
                logger.error(
                    "billing.webhook.transaction_failed",
                    extra={"resolution_type": resolution_type, "outcome": outcome},
                )
                raise ExternalServiceError("Polar webhook processing failed.")

            logger.info(
                "billing.webhook.resolved",
                extra={
                    "resolution_type": resolution_type,
                    "outcome": outcome,
                },
            )


def extract_event_time(
    event: dict[str, Any],
    data: dict[str, Any],
    headers: Mapping[str, str],
) -> datetime:
    event_timestamp = parse_dt(event.get("timestamp"))
    if event_timestamp:
        return event_timestamp.astimezone(UTC)

    provider_timestamp = extract_provider_event_time(data)
    if provider_timestamp:
        return provider_timestamp

    header_value = headers.get("webhook-timestamp") or headers.get("svix-timestamp")
    if header_value:
        try:
            return datetime.fromtimestamp(int(header_value), UTC)
        except ValueError:
            parsed = parse_dt(header_value)
            if parsed:
                return parsed.astimezone(UTC)

    return datetime.now(UTC)


def extract_provider_event_time(data: dict[str, Any]) -> datetime | None:
    """Return an ordered provider timestamp, without inventing a local fallback."""
    for value in (data.get("modified_at"), data.get("updated_at"), data.get("created_at")):
        parsed = parse_dt(value)
        if parsed:
            return parsed.astimezone(UTC)
    return None


def normalize_event_payload(
    event_type: str,
    data: dict[str, Any],
) -> tuple[str | None, str | None, dict[str, Any]]:
    if event_type in {"customer.created", "customer.state_changed"}:
        external_customer_id = as_str(data.get("external_id"))
        billing_address = data.get("billing_address")
        country = as_str(billing_address.get("country")) if isinstance(billing_address, dict) else None
        normalized = {
            "user_id": external_customer_id,
            "external_customer_id": external_customer_id,
            "customer_id": as_str(data.get("id")),
            "email": as_str(data.get("email")),
            "country": country,
        }
        return "customer", as_str(data.get("id")) or external_customer_id, normalized

    if event_type == "order.paid":
        user_id = _extract_user_id(data)
        product_id = _extract_product_id(data)
        order_id = as_str(data.get("id"))
        normalized = {
            "order_id": order_id,
            "user_id": user_id,
            "product_id": product_id,
            "subscription_id": as_str(data.get("subscription_id")),
            "customer_id": as_str(data.get("customer_id")),
            "email": (
                as_str(data.get("customer", {}).get("email")) if isinstance(data.get("customer"), dict) else None
            ),
            "currency": as_str(data.get("currency")),
            "paid_amount_cents": extract_amount_cents(
                data,
                candidates=("total_amount", "net_amount", "amount"),
            ),
        }
        return "order", order_id, normalized

    if event_type == "order.refunded":
        order_id = _extract_refunded_order_id(data)
        provider_total_refunded = _extract_refunded_amount(data)
        normalized = {
            "order_id": order_id,
            "provider_total_refunded": provider_total_refunded,
            "refund_delta_cents": extract_amount_cents(data, candidates=("refund_amount", "amount")),
        }
        return "order", order_id, normalized

    if event_type.startswith("subscription."):
        subscription_id = as_str(data.get("id")) or as_str(data.get("subscription_id"))
        period_start = parse_dt(data.get("current_period_start"))
        period_end = parse_dt(data.get("current_period_end"))
        normalized = {
            "subscription_id": subscription_id,
            "user_id": _extract_user_id(data),
            "product_id": _extract_product_id(data),
            "customer_id": as_str(data.get("customer_id")),
            "status": as_str(data.get("status")) or "unknown",
            "period_start": period_start.astimezone(UTC).isoformat() if period_start else None,
            "period_end": period_end.astimezone(UTC).isoformat() if period_end else None,
        }
        return "subscription", subscription_id, normalized

    return None, None, {}


def _extract_user_id(data: dict[str, Any]) -> str | None:
    user_id = as_str(data.get("customer_external_id"))
    if not user_id:
        customer = data.get("customer")
        if isinstance(customer, dict):
            user_id = as_str(customer.get("external_id"))
    if not user_id:
        metadata = data.get("metadata")
        if isinstance(metadata, dict):
            user_id = as_str(metadata.get("user_id"))
    return user_id


def _extract_product_id(data: dict[str, Any]) -> str | None:
    product_id = as_str(data.get("product_id"))
    if not product_id:
        product = data.get("product")
        if isinstance(product, dict):
            product_id = as_str(product.get("id"))
    return product_id


def _extract_refunded_order_id(data: dict[str, Any]) -> str | None:
    order_id = as_str(data.get("order_id"))
    if order_id:
        return order_id
    nested_order = data.get("order")
    if isinstance(nested_order, dict):
        order_id = as_str(nested_order.get("id"))
        if order_id:
            return order_id
    return as_str(data.get("id"))


def _extract_refunded_amount(data: dict[str, Any]) -> int | None:
    for key in ("refunded_amount", "total_refunded_amount"):
        value = data.get(key)
        if isinstance(value, int):
            return max(value, 0)
        if isinstance(value, str):
            try:
                return max(int(value), 0)
            except ValueError:
                continue
    return None

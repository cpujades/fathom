from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fathom.api.deps.auth import AuthContext
from fathom.core.config import Settings
from fathom.core.errors import ExternalServiceError, InvalidRequestError
from fathom.core.logging import log_context
from fathom.crud.supabase.billing import (
    add_pack_credits,
    fetch_entitlement,
    fetch_plan_by_id,
    fetch_plan_by_price_id,
    fetch_stripe_customer_by_customer_id,
    fetch_stripe_customer_by_user,
    upsert_stripe_customer,
    upsert_subscription_entitlement,
)
from fathom.schemas.billing import CheckoutSessionRequest, CheckoutSessionResponse
from fathom.services.stripe import (
    create_stripe_client,
    get_stripe_cancel_url,
    get_stripe_success_url,
    get_stripe_webhook_secret,
)
from fathom.services.supabase import create_supabase_admin_client

logger = logging.getLogger(__name__)


def _get_value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _extract_event_fields(event: Any) -> tuple[str | None, dict[str, Any] | None]:
    event_type = getattr(event, "type", None)
    data = getattr(event, "data", None)
    if event_type is None and isinstance(event, dict):
        event_type = event.get("type")
        data = event.get("data")
    payload = None
    if data is not None:
        payload = getattr(data, "object", None)
        if payload is None and isinstance(data, dict):
            payload = data.get("object")
    return event_type, payload


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

        plan_type = plan["plan_type"]
        price_id = plan.get("stripe_price_id")
        if plan_type != "subscription" and plan_type != "pack":
            raise InvalidRequestError("Plan type is invalid.")
        if plan_type == "subscription" and price_id == "internal_free":
            raise InvalidRequestError("Free plan does not require checkout.")
        if not price_id:
            raise InvalidRequestError("Plan is missing a Stripe price id.")

        stripe_client = create_stripe_client(settings)
        success_url = get_stripe_success_url(settings)
        cancel_url = get_stripe_cancel_url(settings)

        customer_row = await fetch_stripe_customer_by_user(admin_client, auth.user_id)
        stripe_customer_id = customer_row["stripe_customer_id"] if customer_row else None
        if not stripe_customer_id:
            customer = stripe_client.v1.customers.create(
                params={
                    "metadata": {
                        "user_id": auth.user_id,
                    }
                }
            )
            stripe_customer_id = customer["id"]
            await upsert_stripe_customer(admin_client, user_id=auth.user_id, stripe_customer_id=stripe_customer_id)

        session = stripe_client.v1.checkout.sessions.create(
            params={
                "mode": "subscription" if plan_type == "subscription" else "payment",
                "success_url": success_url,
                "cancel_url": cancel_url,
                "customer": stripe_customer_id,
                "client_reference_id": auth.user_id,
                "line_items": [{"price": price_id, "quantity": 1}],
                "metadata": {
                    "user_id": auth.user_id,
                    "plan_id": plan_id,
                    "price_id": price_id,
                    "plan_type": plan_type,
                },
            }
        )

        checkout_url = session.get("url") if isinstance(session, dict) else getattr(session, "url", None)
        if not checkout_url:
            raise ExternalServiceError("Stripe checkout URL was not returned.")

        logger.info("stripe checkout session created", extra={"session_id": session.get("id")})
        return CheckoutSessionResponse(checkout_url=checkout_url)


async def handle_stripe_webhook(payload: bytes, signature: str | None, settings: Settings) -> None:
    if not signature:
        raise InvalidRequestError("Missing Stripe signature.")

    stripe_client = create_stripe_client(settings)
    secret = get_stripe_webhook_secret(settings)
    event = stripe_client.construct_event(payload, signature, secret)
    event_type, data = _extract_event_fields(event)

    if not event_type or data is None:
        raise InvalidRequestError("Invalid Stripe event payload.")

    admin_client = await create_supabase_admin_client(settings)

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(admin_client, stripe_client, data)
        return

    if event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        await _handle_subscription_event(admin_client, data)
        return

    logger.info("stripe webhook ignored", extra={"event_type": event_type})


async def _handle_checkout_completed(
    admin_client: Any,
    stripe_client: Any,
    session: dict[str, Any],
) -> None:
    customer_id = _get_value(session, "customer")
    metadata = _get_value(session, "metadata") or {}
    user_id = _get_value(session, "client_reference_id") or _get_value(metadata, "user_id")
    if customer_id and user_id:
        await upsert_stripe_customer(admin_client, user_id=user_id, stripe_customer_id=customer_id)

    mode = _get_value(session, "mode")
    if mode == "subscription":
        subscription_id = _get_value(session, "subscription")
        if not subscription_id:
            return
        subscription = stripe_client.v1.subscriptions.retrieve(subscription_id)
        await _apply_subscription(admin_client, subscription)
        return

    if mode == "payment":
        price_id = _get_value(metadata, "price_id")
        if not price_id:
            return
        plan = await fetch_plan_by_price_id(admin_client, price_id)
        if not user_id and customer_id:
            mapping = await fetch_stripe_customer_by_customer_id(admin_client, customer_id)
            user_id = mapping["user_id"] if mapping else None
        if not user_id:
            raise InvalidRequestError("Stripe session missing user mapping.")
        existing = await fetch_entitlement(admin_client, user_id)
        await add_pack_credits(
            admin_client,
            user_id=user_id,
            plan=plan,
            purchased_at=datetime.now(UTC),
            existing=existing,
        )


async def _handle_subscription_event(admin_client: Any, subscription: dict[str, Any]) -> None:
    await _apply_subscription(admin_client, subscription)


async def _apply_subscription(admin_client: Any, subscription: dict[str, Any]) -> None:
    customer_id = _get_value(subscription, "customer")
    if not customer_id:
        return
    mapping = await fetch_stripe_customer_by_customer_id(admin_client, customer_id)
    if not mapping:
        return

    items = _get_value(subscription, "items") or {}
    data_items = _get_value(items, "data") or []
    items_list = list(data_items)
    if not items_list:
        return
    price_obj = _get_value(items_list[0], "price")
    price_id = _get_value(price_obj, "id")
    if not price_id:
        return

    plan = await fetch_plan_by_price_id(admin_client, price_id)
    status = _get_value(subscription, "status") or "unknown"
    period_start = _get_value(subscription, "current_period_start")
    period_end = _get_value(subscription, "current_period_end")
    start_dt = datetime.fromtimestamp(period_start, UTC) if isinstance(period_start, int) else None
    end_dt = datetime.fromtimestamp(period_end, UTC) if isinstance(period_end, int) else None

    existing = await fetch_entitlement(admin_client, mapping["user_id"])
    await upsert_subscription_entitlement(
        admin_client,
        user_id=mapping["user_id"],
        plan=plan,
        status=status,
        period_start=start_dt,
        period_end=end_dt,
        existing=existing,
    )

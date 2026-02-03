from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from postgrest import APIError

from fathom.services.supabase.helpers import first_row, raise_for_postgrest_error
from supabase import AsyncClient


async def fetch_plan_by_id(client: AsyncClient, plan_id: str) -> dict[str, Any]:
    try:
        response = await (
            client.table("plans")
            .select("id,name,plan_type,stripe_price_id,quota_seconds,rollover_cap_seconds,pack_expiry_days,is_active")
            .eq("id", plan_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch plan.")

    return first_row(
        response.data,
        error_message="Supabase returned an unexpected plans shape.",
        not_found_message="Plan not found.",
    )


async def fetch_plan_by_price_id(client: AsyncClient, price_id: str) -> dict[str, Any]:
    try:
        response = await (
            client.table("plans")
            .select("id,name,plan_type,stripe_price_id,quota_seconds,rollover_cap_seconds,pack_expiry_days,is_active")
            .eq("stripe_price_id", price_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch plan by price id.")

    return first_row(
        response.data,
        error_message="Supabase returned an unexpected plans shape.",
        not_found_message="Plan not found for price id.",
    )


async def upsert_stripe_customer(
    client: AsyncClient,
    *,
    user_id: str,
    stripe_customer_id: str,
) -> None:
    try:
        await (
            client.table("stripe_customers")
            .upsert({"user_id": user_id, "stripe_customer_id": stripe_customer_id})
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to upsert Stripe customer.")


async def fetch_stripe_customer_by_user(client: AsyncClient, user_id: str) -> dict[str, Any] | None:
    try:
        response = (
            await client.table("stripe_customers")
            .select("user_id,stripe_customer_id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch Stripe customer.")

    data = response.data or []
    if not data:
        return None
    return cast(dict[str, Any], data[0])


async def fetch_stripe_customer_by_customer_id(client: AsyncClient, stripe_customer_id: str) -> dict[str, Any] | None:
    try:
        response = (
            await client.table("stripe_customers")
            .select("user_id,stripe_customer_id")
            .eq("stripe_customer_id", stripe_customer_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch Stripe customer by id.")

    data = response.data or []
    if not data:
        return None
    return cast(dict[str, Any], data[0])


async def fetch_entitlement(client: AsyncClient, user_id: str) -> dict[str, Any] | None:
    try:
        response = (
            await client.table("entitlements")
            .select(
                "user_id,subscription_plan_id,subscription_status,period_start,period_end,"
                "monthly_quota_seconds,rollover_seconds,pack_seconds_available,pack_expires_at"
            )
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch entitlements.")

    data = response.data or []
    if not data:
        return None
    return cast(dict[str, Any], data[0])


async def upsert_subscription_entitlement(
    client: AsyncClient,
    *,
    user_id: str,
    plan: dict[str, Any],
    status: str,
    period_start: datetime | None,
    period_end: datetime | None,
    existing: dict[str, Any] | None,
) -> None:
    rollover_cap = plan.get("rollover_cap_seconds")
    existing_rollover = 0
    if existing and isinstance(existing.get("rollover_seconds"), int):
        existing_rollover = existing["rollover_seconds"]
    if isinstance(rollover_cap, int):
        existing_rollover = min(existing_rollover, rollover_cap)

    payload = {
        "user_id": user_id,
        "subscription_plan_id": plan["id"],
        "subscription_status": status,
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "monthly_quota_seconds": plan.get("quota_seconds"),
        "rollover_seconds": existing_rollover,
    }

    try:
        await client.table("entitlements").upsert(payload).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to upsert subscription entitlement.")


async def add_pack_credits(
    client: AsyncClient,
    *,
    user_id: str,
    plan: dict[str, Any],
    purchased_at: datetime,
    existing: dict[str, Any] | None,
) -> None:
    pack_seconds = plan.get("quota_seconds") or 0
    pack_expiry_days = plan.get("pack_expiry_days") or 0
    pack_expires_at = purchased_at.replace(tzinfo=UTC) + timedelta(days=pack_expiry_days)

    current_seconds = 0
    current_expires_at = None
    if existing:
        if isinstance(existing.get("pack_seconds_available"), int):
            current_seconds = existing["pack_seconds_available"]
        current_expires_at = existing.get("pack_expires_at")

    if isinstance(current_expires_at, str):
        try:
            parsed = datetime.fromisoformat(current_expires_at)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            current_expires_at = parsed
        except ValueError:
            current_expires_at = None

    if current_expires_at and current_expires_at > purchased_at:
        pack_seconds += current_seconds

    payload = {
        "user_id": user_id,
        "pack_seconds_available": pack_seconds,
        "pack_expires_at": pack_expires_at.isoformat(),
    }

    try:
        await client.table("entitlements").upsert(payload).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to apply pack credits.")

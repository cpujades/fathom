from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from postgrest import APIError
from postgrest.types import CountMethod, ReturnMethod

from fathom.core.errors import ExternalServiceError
from fathom.services.supabase.helpers import raise_for_postgrest_error
from supabase import AsyncClient

ENTITLEMENT_SELECT_FIELDS = (
    "user_id,subscription_plan_id,subscription_status,period_start,period_end,"
    "subscription_cycle_grant_seconds,subscription_rollover_seconds,subscription_available_seconds,"
    "pack_available_seconds,pack_expires_at,debt_seconds,is_blocked,last_balance_sync_at,"
    "polar_subscription_id,provider_event_at,provider_event_id,next_subscription_reconcile_at"
)


async def fetch_entitlement(client: AsyncClient, user_id: str) -> dict[str, Any] | None:
    try:
        response = (
            await client.table("entitlements")
            .select(ENTITLEMENT_SELECT_FIELDS)
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


async def upsert_subscription_entitlement_state(
    client: AsyncClient,
    *,
    user_id: str,
    subscription_plan_id: str | None,
    subscription_status: str,
    period_start: datetime | None,
    period_end: datetime | None,
    subscription_cycle_grant_seconds: int,
    subscription_rollover_seconds: int,
    subscription_available_seconds: int,
) -> None:
    payload: dict[str, Any] = {
        "user_id": user_id,
        "subscription_plan_id": subscription_plan_id,
        "subscription_status": subscription_status,
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "subscription_cycle_grant_seconds": subscription_cycle_grant_seconds,
        "subscription_rollover_seconds": subscription_rollover_seconds,
        "subscription_available_seconds": subscription_available_seconds,
    }

    try:
        await client.table("entitlements").upsert(payload).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to upsert subscription entitlement state.")


async def update_entitlement_snapshot(
    client: AsyncClient,
    *,
    user_id: str,
    subscription_available_seconds: int,
    pack_available_seconds: int,
    pack_expires_at: datetime | None,
    debt_seconds: int,
    is_blocked: bool,
    last_balance_sync_at: datetime,
) -> None:
    payload: dict[str, Any] = {
        "user_id": user_id,
        "subscription_available_seconds": subscription_available_seconds,
        "pack_available_seconds": pack_available_seconds,
        "pack_expires_at": pack_expires_at.isoformat() if pack_expires_at else None,
        "debt_seconds": debt_seconds,
        "is_blocked": is_blocked,
        "last_balance_sync_at": last_balance_sync_at.isoformat(),
    }

    try:
        await client.table("entitlements").upsert(payload).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to update entitlement snapshot.")


async def adjust_entitlement_debt(
    client: AsyncClient,
    *,
    user_id: str,
    delta_seconds: int,
    debt_cap_seconds: int,
    max_retries: int = 5,
) -> int:
    if delta_seconds == 0:
        entitlement = await fetch_entitlement(client, user_id)
        return int(entitlement.get("debt_seconds") or 0) if entitlement else 0

    for _ in range(max_retries):
        entitlement = await fetch_entitlement(client, user_id)
        if not entitlement:
            await client.table("entitlements").upsert({"user_id": user_id}).execute()
            entitlement = await fetch_entitlement(client, user_id)
            if not entitlement:
                continue

        current_debt = int(entitlement.get("debt_seconds") or 0)
        new_debt = max(current_debt + delta_seconds, 0)
        payload: dict[str, Any] = {
            "debt_seconds": new_debt,
            "is_blocked": new_debt >= debt_cap_seconds,
            "last_balance_sync_at": datetime.now(UTC).isoformat(),
        }
        try:
            response = (
                await client.table("entitlements")
                .update(payload, count=CountMethod.exact, returning=ReturnMethod.minimal)
                .eq("user_id", user_id)
                .eq("debt_seconds", current_debt)
                .execute()
            )
        except APIError as exc:
            raise_for_postgrest_error(exc, "Failed to adjust entitlement debt.")

        if int(response.count or 0) > 0:
            return new_debt

    raise ExternalServiceError("Failed to adjust entitlement debt due to concurrent updates.")

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from postgrest import APIError

from fathom.services.supabase.helpers import raise_for_postgrest_error, response_records
from supabase import AsyncClient

ORDER_SELECT_FIELDS = (
    "id,polar_order_id,user_id,plan_id,plan_type,polar_product_id,polar_subscription_id,"
    "currency,paid_amount_cents,refunded_amount_cents,status,created_at,updated_at"
)

ENTITLEMENT_SELECT_FIELDS = (
    "user_id,subscription_plan_id,subscription_status,period_start,period_end,"
    "subscription_cycle_grant_seconds,subscription_rollover_seconds,subscription_available_seconds,"
    "pack_available_seconds,pack_expires_at,debt_seconds,is_blocked,last_balance_sync_at,"
    "polar_subscription_id,provider_event_at,provider_event_id,next_subscription_reconcile_at"
)


async def list_billing_orders_for_user(
    client: AsyncClient,
    *,
    user_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    try:
        response = (
            await client.table("billing_orders")
            .select(ORDER_SELECT_FIELDS)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to list billing orders for user.")

    return [cast(dict[str, Any], row) for row in (response.data or []) if isinstance(row, dict)]


async def fetch_polar_order_ids_refund_pending(client: AsyncClient, user_id: str) -> list[str]:
    try:
        response = (
            await client.table("billing_orders")
            .select("polar_order_id")
            .eq("user_id", user_id)
            .eq("status", "refund_pending")
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch refund-pending orders.")

    rows = response_records(
        response.data,
        error_message="Supabase returned an unexpected billing orders shape.",
    )
    return [str(row["polar_order_id"]) for row in rows if row.get("polar_order_id")]


async def list_refund_pending_pack_orders(
    client: AsyncClient,
    *,
    updated_before: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    try:
        response = (
            await client.table("billing_orders")
            .select(ORDER_SELECT_FIELDS)
            .eq("plan_type", "pack")
            .eq("status", "refund_pending")
            .lt("updated_at", updated_before.isoformat())
            .order("updated_at", desc=False)
            .limit(limit)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to list refund-pending pack orders.")

    return [cast(dict[str, Any], row) for row in (response.data or []) if isinstance(row, dict)]


async def list_subscription_entitlements_for_reconciliation(
    client: AsyncClient,
    *,
    due_at: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    try:
        response = (
            await client.table("entitlements")
            .select(ENTITLEMENT_SELECT_FIELDS)
            .not_.is_("polar_subscription_id", "null")
            .not_.is_("next_subscription_reconcile_at", "null")
            .lte("next_subscription_reconcile_at", due_at.isoformat())
            .order("next_subscription_reconcile_at", desc=False)
            .limit(limit)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to list subscription entitlements for reconciliation.")

    return [cast(dict[str, Any], row) for row in (response.data or []) if isinstance(row, dict)]


async def schedule_subscription_reconciliation(
    client: AsyncClient,
    *,
    user_id: str,
    next_reconcile_at: datetime | None,
) -> None:
    try:
        await (
            client.table("entitlements")
            .update(
                {
                    "next_subscription_reconcile_at": (
                        next_reconcile_at.isoformat() if next_reconcile_at is not None else None
                    )
                }
            )
            .eq("user_id", user_id)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to schedule subscription reconciliation.")

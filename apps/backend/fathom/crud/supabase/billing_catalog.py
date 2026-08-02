from __future__ import annotations

from typing import Any, cast

from postgrest import APIError

from fathom.services.supabase.helpers import first_row, raise_for_postgrest_error
from supabase import AsyncClient

PLAN_SELECT_FIELDS = (
    "id,name,plan_code,plan_type,polar_product_id,currency,amount_cents,billing_interval,version,"
    "quota_seconds,rollover_cap_seconds,pack_expiry_days,is_active"
)


async def fetch_plan_by_id(client: AsyncClient, plan_id: str) -> dict[str, Any]:
    try:
        response = await client.table("plans").select(PLAN_SELECT_FIELDS).eq("id", plan_id).limit(1).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch plan.")

    return first_row(
        response.data,
        error_message="Supabase returned an unexpected plans shape.",
        not_found_message="Plan not found.",
    )


async def fetch_plan_by_product_id(client: AsyncClient, product_id: str) -> dict[str, Any]:
    try:
        response = (
            await client.table("plans").select(PLAN_SELECT_FIELDS).eq("polar_product_id", product_id).limit(1).execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch plan by product id.")

    return first_row(
        response.data,
        error_message="Supabase returned an unexpected plans shape.",
        not_found_message="Plan not found for Polar product id.",
    )


async def fetch_active_plans(client: AsyncClient) -> list[dict[str, Any]]:
    try:
        response = (
            await client.table("plans")
            .select(PLAN_SELECT_FIELDS)
            .eq("is_active", True)
            .order("plan_type", desc=False)
            .order("amount_cents", desc=False)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch plans.")

    return [cast(dict[str, Any], row) for row in (response.data or []) if isinstance(row, dict)]


async def fetch_plan_names_by_ids(client: AsyncClient, *, plan_ids: set[str]) -> dict[str, str]:
    if not plan_ids:
        return {}

    try:
        response = await client.table("plans").select("id,name").in_("id", list(plan_ids)).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch plan names.")

    rows = [cast(dict[str, Any], row) for row in (response.data or []) if isinstance(row, dict)]
    return {str(row["id"]): str(row["name"]) for row in rows if row.get("id") and row.get("name")}

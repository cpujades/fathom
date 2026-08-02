from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from postgrest import APIError

from fathom.core.errors import ExternalServiceError
from fathom.services.supabase.helpers import raise_for_postgrest_error
from supabase import AsyncClient


async def fetch_usage_history(
    client: AsyncClient,
    *,
    user_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    try:
        response = (
            await client.table("usage_ledger")
            .select("job_id,seconds_used,source,created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch usage history.")

    return [cast(dict[str, Any], row) for row in (response.data or []) if isinstance(row, dict)]


async def settle_job_usage(
    client: AsyncClient,
    *,
    job_id: str,
    lease_token: str,
    debt_cap_seconds: int,
) -> dict[str, Any]:
    """Atomically settle one lease-owned job, returning the immutable settlement."""
    try:
        response = await client.rpc(
            "settle_job_usage",
            {
                "p_job_id": job_id,
                "p_lease_token": lease_token,
                "p_debt_cap_seconds": debt_cap_seconds,
            },
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to settle job usage.")

    if not isinstance(response.data, Mapping):
        raise ExternalServiceError("Supabase returned an unexpected usage settlement shape.")

    result = dict(response.data)
    if result.get("resolution_type") not in {"settled", "already_settled"} or not isinstance(
        result.get("settlement"), Mapping
    ):
        raise ExternalServiceError("Supabase returned an unexpected usage settlement shape.")
    return result

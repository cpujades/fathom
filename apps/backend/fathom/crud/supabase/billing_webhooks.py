from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from postgrest import APIError
from postgrest.types import CountMethod, ReturnMethod

from fathom.core.errors import ExternalServiceError
from fathom.services.supabase.helpers import raise_for_postgrest_error
from supabase import AsyncClient


async def upsert_polar_customer(
    client: AsyncClient,
    *,
    user_id: str,
    external_customer_id: str,
    polar_customer_id: str | None = None,
    email: str | None = None,
    country: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "user_id": user_id,
        "external_customer_id": external_customer_id,
    }
    if polar_customer_id:
        payload["polar_customer_id"] = polar_customer_id
    if email is not None:
        payload["email"] = email
    if country is not None:
        payload["country"] = country

    try:
        await client.table("polar_customers").upsert(payload, on_conflict="user_id").execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to upsert Polar customer.")


async def reclaim_stale_webhook_processing(
    client: AsyncClient,
    *,
    stale_minutes: int = 15,
) -> int:
    """Return crashed webhook events to a retryable state."""
    stale_before = (datetime.now(UTC) - timedelta(minutes=stale_minutes)).isoformat()
    try:
        response = (
            await client.table("billing_webhook_events")
            .update(
                {
                    "status": "failed",
                    "processed_at": datetime.now(UTC).isoformat(),
                    "error": "stale processing state reclaimed by scheduled job",
                },
                count=CountMethod.exact,
                returning=ReturnMethod.minimal,
            )
            .eq("status", "processing")
            .is_("processed_at", "null")
            .lt("received_at", stale_before)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to reclaim stale webhook processing state.")
    return int(response.count or 0)


async def apply_polar_webhook_transaction(
    client: AsyncClient,
    *,
    event_id: str,
    event_type: str,
    event_at: datetime,
    resource_type: str | None,
    resource_id: str | None,
    payload: dict[str, Any],
    debt_cap_seconds: int,
) -> dict[str, Any]:
    """Atomically record and apply one normalized Polar event."""
    try:
        response = await client.rpc(
            "apply_polar_webhook_event",
            {
                "p_event_id": event_id,
                "p_event_type": event_type,
                "p_event_at": event_at.isoformat(),
                "p_resource_type": resource_type,
                "p_resource_id": resource_id,
                "p_payload": payload,
                "p_debt_cap_seconds": debt_cap_seconds,
            },
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to apply Polar webhook event.")

    if not isinstance(response.data, Mapping):
        raise ExternalServiceError("Supabase returned an unexpected Polar webhook resolution shape.")

    result = dict(response.data)
    if result.get("resolution_type") not in {
        "processed",
        "already_processed",
        "deferred",
        "failed",
    }:
        raise ExternalServiceError("Supabase returned an unexpected Polar webhook resolution shape.")
    return result

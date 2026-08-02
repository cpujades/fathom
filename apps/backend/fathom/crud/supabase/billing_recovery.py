from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from postgrest import APIError

from fathom.core.errors import ExternalServiceError
from fathom.services.supabase.helpers import raise_for_postgrest_error, response_record
from supabase import AsyncClient

PACK_REFUND_RESOLUTIONS = {
    "started",
    "not_found",
    "not_pack",
    "already_pending",
    "already_refunded",
    "lot_not_found",
    "not_refundable",
    "nothing_remaining",
}

PACK_REFUND_REOPEN_RESOLUTIONS = {
    "reopened",
    "not_found",
    "not_pack",
    "already_refunded",
    "already_paid",
}


async def begin_pack_refund(
    client: AsyncClient,
    *,
    user_id: str,
    polar_order_id: str,
    debt_cap_seconds: int,
) -> dict[str, Any]:
    """Atomically quote and start a pack refund against current lot state."""
    try:
        response = await client.rpc(
            "begin_pack_refund",
            {
                "p_user_id": user_id,
                "p_order_id": polar_order_id,
                "p_debt_cap_seconds": debt_cap_seconds,
            },
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to begin pack refund.")

    if not isinstance(response.data, Mapping):
        raise ExternalServiceError("Supabase returned an unexpected pack refund resolution shape.")
    result = dict(response.data)
    if result.get("resolution_type") not in PACK_REFUND_RESOLUTIONS:
        raise ExternalServiceError("Supabase returned an unexpected pack refund resolution shape.")
    return result


async def reopen_pack_refund(
    client: AsyncClient,
    *,
    user_id: str,
    polar_order_id: str,
    debt_cap_seconds: int,
) -> dict[str, Any]:
    """Atomically reopen a pending pack after Polar proves no refund exists."""
    try:
        response = await client.rpc(
            "reopen_pack_refund",
            {
                "p_user_id": user_id,
                "p_order_id": polar_order_id,
                "p_debt_cap_seconds": debt_cap_seconds,
            },
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to reopen pack refund.")

    if not isinstance(response.data, Mapping):
        raise ExternalServiceError("Supabase returned an unexpected pack refund reopen shape.")
    result = dict(response.data)
    if result.get("resolution_type") not in PACK_REFUND_REOPEN_RESOLUTIONS:
        raise ExternalServiceError("Supabase returned an unexpected pack refund reopen shape.")
    return result


async def claim_billing_maintenance_lease(
    client: AsyncClient,
    *,
    lease_name: str,
    lease_token: str,
    lease_seconds: int,
) -> bool:
    try:
        response = await client.rpc(
            "claim_billing_maintenance_lease",
            {
                "p_lease_name": lease_name,
                "p_lease_token": lease_token,
                "p_lease_for": f"{lease_seconds} seconds",
            },
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to claim billing maintenance lease.")
    return response.data is True


async def renew_billing_maintenance_lease(
    client: AsyncClient,
    *,
    lease_name: str,
    lease_token: str,
    lease_seconds: int,
) -> bool:
    try:
        response = await client.rpc(
            "renew_billing_maintenance_lease",
            {
                "p_lease_name": lease_name,
                "p_lease_token": lease_token,
                "p_lease_for": f"{lease_seconds} seconds",
            },
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to renew billing maintenance lease.")
    return response.data is True


async def release_billing_maintenance_lease(
    client: AsyncClient,
    *,
    lease_name: str,
    lease_token: str,
) -> bool:
    try:
        response = await client.rpc(
            "release_billing_maintenance_lease",
            {"p_lease_name": lease_name, "p_lease_token": lease_token},
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to release billing maintenance lease.")
    return response.data is True


async def get_billing_webhook_diagnostics(
    client: AsyncClient,
    *,
    stale_minutes: int = 5,
) -> dict[str, Any]:
    """Return non-sensitive counts for unresolved or stale webhook work."""
    try:
        response = await client.rpc(
            "get_billing_webhook_diagnostics",
            {"p_stale_after": f"{stale_minutes} minutes"},
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch billing webhook diagnostics.")

    return response_record(
        response.data,
        error_message="Supabase returned an unexpected billing webhook diagnostic shape.",
    )

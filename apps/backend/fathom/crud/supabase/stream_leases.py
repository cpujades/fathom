from __future__ import annotations

from postgrest.exceptions import APIError

from fathom.core.errors import ExternalServiceError
from fathom.services.supabase import raise_for_postgrest_error
from supabase import AsyncClient


async def claim_stream_lease(
    client: AsyncClient,
    *,
    user_id: str,
    client_subject: str,
    max_per_user: int,
    max_per_subject: int,
    lease_seconds: int,
) -> str | None:
    try:
        response = await client.rpc(
            "claim_briefing_stream_lease",
            {
                "p_user_id": user_id,
                "p_client_subject": client_subject,
                "p_max_per_user": max_per_user,
                "p_max_per_subject": max_per_subject,
                "p_lease_seconds": lease_seconds,
            },
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to reserve a briefing event stream.")
    token = response.data
    if token is None:
        return None
    if not isinstance(token, str) or not token:
        raise ExternalServiceError("Supabase returned an invalid stream lease.")
    return token


async def renew_stream_lease(
    client: AsyncClient,
    *,
    lease_token: str,
    lease_seconds: int,
) -> bool:
    try:
        response = await client.rpc(
            "renew_briefing_stream_lease",
            {"p_lease_token": lease_token, "p_lease_seconds": lease_seconds},
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to renew a briefing event stream.")
    return response.data is True


async def release_stream_lease(client: AsyncClient, *, lease_token: str) -> None:
    try:
        response = await client.rpc(
            "release_briefing_stream_lease",
            {"p_lease_token": lease_token},
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to release a briefing event stream.")
    if response.data is not True:
        raise ExternalServiceError("Supabase could not release the briefing event stream.")

"""Supabase transcripts CRUD."""

from __future__ import annotations

from typing import Any

from postgrest import APIError

from app.services.supabase.helpers import first_row, raise_for_postgrest_error
from supabase import AsyncClient


async def fetch_transcript_by_hash(
    client: AsyncClient,
    *,
    url_hash: str,
    provider_model: str,
) -> dict[str, Any] | None:
    try:
        response = await (
            client.table("transcripts")
            .select("id,transcript_text,video_id,provider_model,url_hash")
            .eq("url_hash", url_hash)
            .eq("provider_model", provider_model)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch transcript.")

    data = response.data or []
    if not data:
        return None

    return first_row(data, error_message="Supabase returned an unexpected transcripts shape.")


async def create_transcript(
    client: AsyncClient,
    *,
    url_hash: str,
    video_id: str | None,
    transcript_text: str,
    provider_model: str,
) -> dict[str, Any]:
    try:
        response = (
            await client.table("transcripts")
            .insert(
                {
                    "url_hash": url_hash,
                    "video_id": video_id,
                    "transcript_text": transcript_text,
                    "provider_model": provider_model,
                }
            )
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to create transcript.")

    return first_row(response.data, error_message="Failed to create transcript.")

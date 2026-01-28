"""Supabase transcripts CRUD."""

from __future__ import annotations

from typing import Any

from postgrest import APIError

from fathom.services.supabase.helpers import first_row, is_unique_violation, raise_for_postgrest_error
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


async def fetch_transcript_by_video_id(
    client: AsyncClient,
    *,
    video_id: str,
    provider_model: str,
) -> dict[str, Any] | None:
    try:
        response = await (
            client.table("transcripts")
            .select("id,transcript_text,video_id,provider_model,url_hash")
            .eq("video_id", video_id)
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
    payload = {
        "url_hash": url_hash,
        "video_id": video_id,
        "transcript_text": transcript_text,
        "provider_model": provider_model,
    }

    try:
        response = await client.table("transcripts").insert(payload).execute()
    except APIError as exc:
        # Make the insert idempotent under retries/races.
        if is_unique_violation(exc):
            existing = await fetch_transcript_by_hash(
                client,
                url_hash=url_hash,
                provider_model=provider_model,
            )
            if existing:
                return existing
        raise_for_postgrest_error(exc, "Failed to create transcript.")

    return first_row(response.data, error_message="Failed to create transcript.")


async def fetch_transcript_by_id(client: AsyncClient, transcript_id: str) -> dict[str, Any]:
    """Fetch a transcript by ID."""
    try:
        response = await client.table("transcripts").select("id,video_id").eq("id", transcript_id).limit(1).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch transcript.")

    return first_row(
        response.data,
        error_message="Supabase returned an unexpected transcripts shape.",
        not_found_message="Transcript not found.",
    )

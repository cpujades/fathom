"""Supabase transcripts CRUD."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from postgrest import APIError

from fathom.core.errors import ExternalServiceError
from fathom.schemas.transcripts import TranscriptSegment
from fathom.services.supabase.helpers import (
    first_row,
    is_unique_violation,
    raise_for_postgrest_error,
    response_record,
    response_records,
)
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
    segments: tuple[TranscriptSegment, ...] = (),
    source_title: str | None = None,
    source_author: str | None = None,
    source_description: str | None = None,
    source_keywords: list[str] | None = None,
    source_views: int | None = None,
    source_likes: int | None = None,
    source_length_seconds: int | None = None,
) -> dict[str, Any]:
    payload = {
        "p_url_hash": url_hash,
        "p_video_id": video_id,
        "p_transcript_text": transcript_text,
        "p_provider_model": provider_model,
        "p_segments": [
            {
                "segment_index": segment.segment_index,
                "start_seconds": segment.start_seconds,
                "end_seconds": segment.end_seconds,
                "text": segment.text,
            }
            for segment in segments
        ],
        "p_source_title": source_title,
        "p_source_author": source_author,
        "p_source_description": source_description,
        "p_source_keywords": source_keywords,
        "p_source_views": source_views,
        "p_source_likes": source_likes,
        "p_source_length_seconds": source_length_seconds,
    }

    try:
        response = await client.rpc("create_transcript_with_segments", payload).execute()
    except APIError as exc:
        # Preserve compatibility with races against an older worker during rollout.
        if is_unique_violation(exc):
            existing = await fetch_transcript_by_hash(
                client,
                url_hash=url_hash,
                provider_model=provider_model,
            )
            if existing:
                return existing
        raise_for_postgrest_error(exc, "Failed to create transcript.")

    if isinstance(response.data, Mapping):
        return response_record(response.data, error_message="Failed to create transcript.")
    return first_row(response.data, error_message="Failed to create transcript.")


async def fetch_transcript_segments(
    client: AsyncClient,
    *,
    transcript_id: str,
) -> tuple[TranscriptSegment, ...]:
    try:
        response = await (
            client.table("transcript_segments")
            .select("segment_index,start_seconds,end_seconds,segment_text")
            .eq("transcript_id", transcript_id)
            .order("segment_index")
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch transcript segments.")

    segments: list[TranscriptSegment] = []
    rows = response_records(
        response.data,
        error_message="Supabase returned invalid transcript segments.",
    )
    for expected_index, row in enumerate(rows):
        segment_index = row.get("segment_index")
        start_seconds = row.get("start_seconds")
        end_seconds = row.get("end_seconds")
        text = row.get("segment_text")
        if (
            not isinstance(segment_index, int)
            or isinstance(segment_index, bool)
            or not isinstance(start_seconds, (int, float))
            or isinstance(start_seconds, bool)
            or not isinstance(end_seconds, (int, float))
            or isinstance(end_seconds, bool)
            or not isinstance(text, str)
        ):
            raise ExternalServiceError("Supabase returned invalid transcript segments.")
        try:
            segment = TranscriptSegment(
                segment_index=segment_index,
                start_seconds=float(start_seconds),
                end_seconds=float(end_seconds),
                text=text,
            )
        except ValueError as exc:
            raise ExternalServiceError("Supabase returned invalid transcript segments.") from exc
        if segment.segment_index != expected_index:
            raise ExternalServiceError("Supabase returned non-contiguous transcript segments.")
        segments.append(segment)

    return tuple(segments)


async def fetch_transcript_by_id(client: AsyncClient, transcript_id: str) -> dict[str, Any]:
    """Fetch a transcript by ID."""
    try:
        response = await (
            client.table("transcripts")
            .select("id,video_id,source_title,source_author,source_length_seconds")
            .eq("id", transcript_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch transcript.")

    return first_row(
        response.data,
        error_message="Supabase returned an unexpected transcripts shape.",
        not_found_message="Transcript not found.",
    )


async def fetch_transcripts_by_ids(client: AsyncClient, transcript_ids: list[str]) -> list[dict[str, Any]]:
    if not transcript_ids:
        return []

    try:
        response = await (
            client.table("transcripts")
            .select("id,video_id,source_title,source_author,source_length_seconds")
            .in_("id", transcript_ids)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch transcripts.")

    return response_records(
        response.data,
        error_message="Supabase returned an unexpected transcripts shape.",
    )

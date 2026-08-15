"""Supabase publication CRUD."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from postgrest import APIError
from postgrest.types import CountMethod

from fathom.core.errors import ConflictError, ExternalServiceError, NotFoundError
from fathom.services.supabase.helpers import (
    first_row,
    is_unique_violation,
    raise_for_postgrest_error,
    response_record,
    response_records,
)
from supabase import AsyncClient

PUBLICATION_FIELDS = (
    "id,owner_user_id,owner_job_id,summary_id,source_key,public_slug,visibility,topic,"
    "listed_at,moderation_status,published_at,unpublished_at,created_at,updated_at"
)


async def fetch_owner_publication(
    client: AsyncClient,
    *,
    owner_job_id: str,
) -> dict[str, Any] | None:
    try:
        response = await (
            client.table("briefing_publications")
            .select(PUBLICATION_FIELDS)
            .eq("owner_job_id", owner_job_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch publication state.")

    rows = response_records(response.data, error_message="Supabase returned an unexpected publication shape.")
    return rows[0] if rows else None


async def create_publication(
    client: AsyncClient,
    *,
    owner_user_id: str,
    owner_job_id: str,
    summary_id: str,
    visibility: str,
    topic: str | None,
) -> dict[str, Any]:
    """Create a publication or complete a concurrent creation for the same job."""
    now_fields = _publication_time_fields(visibility, publication=None)
    try:
        response = await (
            client.table("briefing_publications")
            .upsert(
                {
                    "owner_user_id": owner_user_id,
                    "owner_job_id": owner_job_id,
                    "summary_id": summary_id,
                    "visibility": visibility,
                    "topic": topic,
                    **now_fields,
                },
                on_conflict="owner_job_id",
                default_to_null=False,
            )
            .execute()
        )
    except APIError as exc:
        if visibility == "listed" and is_unique_violation(exc):
            raise ConflictError("This source is already in Explore.") from exc
        raise_for_postgrest_error(exc, "Failed to publish briefing.")

    return first_row(response.data, error_message="Supabase returned an unexpected publication shape.")


async def update_publication(
    client: AsyncClient,
    *,
    publication: dict[str, Any],
    visibility: str,
    topic: str | None,
) -> dict[str, Any]:
    publication_id = publication.get("id")
    if not publication_id:
        raise ExternalServiceError("Supabase returned an unexpected publication shape.")

    payload = {
        "visibility": visibility,
        "topic": topic,
        **_publication_time_fields(visibility, publication=publication),
    }
    try:
        response = await client.table("briefing_publications").update(payload).eq("id", str(publication_id)).execute()
    except APIError as exc:
        if visibility == "listed" and is_unique_violation(exc):
            raise ConflictError("This source is already in Explore.") from exc
        raise_for_postgrest_error(exc, "Failed to update publication.")

    return first_row(response.data, error_message="Supabase returned an unexpected publication shape.")


async def fetch_public_publication(
    client: AsyncClient,
    *,
    public_slug: str,
) -> dict[str, Any] | None:
    try:
        response = await (
            client.table("briefing_publications")
            .select(PUBLICATION_FIELDS)
            .eq("public_slug", public_slug)
            .in_("visibility", ["unlisted", "listed"])
            .eq("moderation_status", "clear")
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch public briefing.")

    rows = response_records(response.data, error_message="Supabase returned an unexpected publication shape.")
    return rows[0] if rows else None


async def fetch_public_publications_by_slugs(
    client: AsyncClient,
    *,
    public_slugs: list[str],
) -> list[dict[str, Any]]:
    if not public_slugs:
        return []

    try:
        response = await (
            client.table("briefing_publications")
            .select("public_slug,source_key")
            .in_("public_slug", public_slugs)
            .in_("visibility", ["unlisted", "listed"])
            .eq("moderation_status", "clear")
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch public briefings.")

    return response_records(
        response.data,
        error_message="Supabase returned an unexpected public briefing shape.",
    )


async def fetch_library_jobs_for_sources(
    client: AsyncClient,
    *,
    user_id: str,
    source_keys: list[str],
) -> list[dict[str, Any]]:
    if not source_keys:
        return []

    try:
        response = await (
            client.table("jobs")
            .select("id,status,source_key,created_at")
            .eq("user_id", user_id)
            .in_("source_key", source_keys)
            .in_("status", ["queued", "running", "succeeded", "deleted"])
            .order("created_at", desc=True)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch library state.")

    return response_records(
        response.data,
        error_message="Supabase returned an unexpected library state shape.",
    )


async def fetch_listed_publication_for_source(
    client: AsyncClient,
    *,
    source_key: str,
) -> dict[str, Any] | None:
    try:
        response = await (
            client.table("briefing_publications")
            .select(PUBLICATION_FIELDS)
            .eq("source_key", source_key)
            .eq("visibility", "listed")
            .eq("moderation_status", "clear")
            .order("listed_at", desc=True)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to match a public briefing.")

    rows = response_records(response.data, error_message="Supabase returned an unexpected publication shape.")
    return rows[0] if rows else None


async def fetch_listed_publications_page(
    client: AsyncClient,
    *,
    limit: int,
    offset: int,
    topic: str | None,
) -> tuple[list[dict[str, Any]], int]:
    try:
        query = (
            client.table("briefing_publications")
            .select(PUBLICATION_FIELDS, count=CountMethod.exact)
            .eq("visibility", "listed")
            .eq("moderation_status", "clear")
        )
        if topic:
            query = query.eq("topic", topic)
        response = (
            await query.order("listed_at", desc=True)
            .order("id", desc=True)
            .range(offset, max(offset + limit - 1, offset))
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch Explore briefings.")

    rows = response_records(response.data, error_message="Supabase returned an unexpected publication shape.")
    count = response.count if isinstance(response.count, int) else len(rows)
    return rows, count


async def fetch_publication_job(client: AsyncClient, *, job_id: str) -> dict[str, Any]:
    try:
        response = await (
            client.table("jobs")
            .select("id,user_id,status,url,source_key,summary_id,duration_seconds,created_at")
            .eq("id", job_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch publication source.")

    return first_row(
        response.data,
        error_message="Supabase returned an unexpected publication source shape.",
        not_found_message="Public briefing not found.",
    )


async def save_publication(
    client: AsyncClient,
    *,
    user_id: str,
    public_slug: str,
) -> dict[str, Any]:
    try:
        response = await client.rpc(
            "save_briefing_publication",
            {
                "p_user_id": user_id,
                "p_public_slug": public_slug,
            },
        ).execute()
    except APIError as exc:
        if (getattr(exc, "code", None) or "") == "P0002":
            raise NotFoundError("Public briefing not found.") from exc
        raise_for_postgrest_error(exc, "Failed to save public briefing.")

    if isinstance(response.data, Mapping):
        result = dict(response.data)
    else:
        result = first_row(response.data, error_message="Supabase returned an unexpected save result.")
    if not isinstance(result.get("job"), Mapping):
        raise ExternalServiceError("Supabase returned an unexpected save result.")
    return response_record(result, error_message="Supabase returned an unexpected save result.")


def _publication_time_fields(
    visibility: str,
    *,
    publication: dict[str, Any] | None,
) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    published_at = publication.get("published_at") if publication else None
    unpublished_at = publication.get("unpublished_at") if publication else None
    if visibility == "private":
        return (
            {
                "listed_at": None,
                "unpublished_at": unpublished_at or now,
            }
            if published_at
            else {
                "listed_at": None,
                "published_at": None,
                "unpublished_at": None,
            }
        )

    fields: dict[str, Any] = {
        "listed_at": (
            (publication.get("listed_at") if publication else None) or now if visibility == "listed" else None
        ),
        "unpublished_at": None,
    }
    if not published_at:
        fields["published_at"] = now
    return fields

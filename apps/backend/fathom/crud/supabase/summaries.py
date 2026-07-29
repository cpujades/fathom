"""Supabase summaries CRUD."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from postgrest import APIError

from fathom.core.errors import ExternalServiceError
from fathom.services.supabase.helpers import first_row, raise_for_postgrest_error
from supabase import AsyncClient


class SummaryGenerationLostError(RuntimeError):
    """The worker no longer owns the pending summary generation."""


SummaryPreparationType = Literal["created", "ready", "in_progress", "taken_over"]


@dataclass(frozen=True)
class SummaryPreparation:
    summary: dict[str, Any]
    resolution_type: SummaryPreparationType


def _summary_select_query(client: AsyncClient) -> Any:
    """Return the base summaries select query with the fields we need."""
    return client.table("summaries").select(
        "id,user_id,transcript_id,summary_markdown,pdf_object_key,status,status_updated_at,ready_at,failed_at"
    )


async def fetch_summary(client: AsyncClient, summary_id: str) -> dict[str, Any]:
    """Fetch a summary by ID."""
    try:
        response = await _summary_select_query(client).eq("id", summary_id).limit(1).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch summary.")

    return first_row(
        response.data,
        error_message="Supabase returned an unexpected summaries shape.",
        not_found_message="Summary not found.",
    )


async def fetch_summaries_by_ids(client: AsyncClient, summary_ids: list[str]) -> list[dict[str, Any]]:
    if not summary_ids:
        return []

    try:
        response = await client.table("summaries").select("id,transcript_id").in_("id", summary_ids).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch summaries.")

    data = response.data or []
    return [row for row in data if isinstance(row, dict)]


async def fetch_summary_by_keys(
    client: AsyncClient,
    *,
    transcript_id: str,
    prompt_key: str,
    summary_model: str,
) -> dict[str, Any] | None:
    """Fetch a summary by its global cache key."""
    try:
        response = await (
            _summary_select_query(client)
            .eq("transcript_id", transcript_id)
            .eq("prompt_key", prompt_key)
            .eq("summary_model", summary_model)
            .eq("status", "ready")
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch summary by keys.")

    data = response.data or []
    if not data:
        return None

    return first_row(data, error_message="Supabase returned an unexpected summaries shape.")


async def prepare_summary(
    client: AsyncClient,
    *,
    summary_id: str,
    user_id: str,
    job_id: str,
    generation_token: str,
    transcript_id: str,
    prompt_key: str,
    summary_model: str,
) -> SummaryPreparation:
    try:
        response = await client.rpc(
            "prepare_summary",
            {
                "p_summary_id": summary_id,
                "p_user_id": user_id,
                "p_job_id": job_id,
                "p_generation_token": generation_token,
                "p_transcript_id": transcript_id,
                "p_prompt_key": prompt_key,
                "p_summary_model": summary_model,
            },
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to prepare summary generation.")

    data = response.data
    if isinstance(data, Mapping):
        result = dict(data)
    else:
        result = first_row(data, error_message="Supabase returned an unexpected summary preparation shape.")

    resolution_type = result.get("resolution_type")
    summary = result.get("summary")
    if resolution_type not in {"created", "ready", "in_progress", "taken_over"} or not isinstance(summary, Mapping):
        raise ExternalServiceError("Supabase returned an unexpected summary preparation shape.")

    return SummaryPreparation(summary=dict(summary), resolution_type=resolution_type)


async def update_summary_pdf_key(
    client: AsyncClient,
    *,
    summary_id: str,
    pdf_object_key: str,
) -> dict[str, Any]:
    """Update the PDF object key for a summary."""
    try:
        response = (
            await client.table("summaries")
            .update({"pdf_object_key": pdf_object_key})
            .eq("id", summary_id)
            .eq("status", "ready")
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to update summary PDF key.")

    return first_row(response.data, error_message="Failed to update summary PDF key.")


async def update_summary_markdown(
    client: AsyncClient,
    *,
    summary_id: str,
    generation_token: str,
    summary_markdown: str,
) -> None:
    try:
        response = await client.rpc(
            "update_summary_draft",
            {
                "p_summary_id": summary_id,
                "p_generation_token": generation_token,
                "p_summary_markdown": summary_markdown,
            },
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to update summary markdown.")

    if response.data is not True:
        raise SummaryGenerationLostError(f"Summary generation ownership lost for {summary_id}.")


async def mark_summary_ready(
    client: AsyncClient,
    *,
    summary_id: str,
    generation_token: str,
    summary_markdown: str,
) -> None:
    try:
        response = await client.rpc(
            "complete_summary_generation",
            {
                "p_summary_id": summary_id,
                "p_generation_token": generation_token,
                "p_summary_markdown": summary_markdown,
            },
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to complete summary generation.")

    if response.data is not True:
        raise SummaryGenerationLostError(f"Summary generation ownership lost for {summary_id}.")


async def mark_summary_failed(
    client: AsyncClient,
    *,
    summary_id: str,
    generation_token: str,
) -> bool:
    try:
        response = await client.rpc(
            "fail_summary_generation",
            {
                "p_summary_id": summary_id,
                "p_generation_token": generation_token,
            },
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to mark summary generation failed.")

    return response.data is True

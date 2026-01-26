"""Supabase summaries CRUD."""

from __future__ import annotations

from typing import Any

from postgrest import APIError

from app.services.supabase.helpers import first_row, raise_for_postgrest_error
from supabase import AsyncClient


async def fetch_summary(client: AsyncClient, summary_id: str) -> dict[str, Any]:
    """Fetch a summary by ID."""
    try:
        response = await (
            client.table("summaries")
            .select("id,user_id,transcript_id,summary_markdown,pdf_object_key")
            .eq("id", summary_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch summary.")

    return first_row(
        response.data,
        error_message="Supabase returned an unexpected summaries shape.",
        not_found_message="Summary not found.",
    )


async def create_summary(
    client: AsyncClient,
    *,
    summary_id: str,
    user_id: str,
    transcript_id: str,
    prompt_key: str,
    summary_model: str,
    summary_markdown: str,
    pdf_object_key: str | None,
) -> dict[str, Any]:
    try:
        response = (
            await client.table("summaries")
            .insert(
                {
                    "id": summary_id,
                    "user_id": user_id,
                    "transcript_id": transcript_id,
                    "prompt_key": prompt_key,
                    "summary_model": summary_model,
                    "summary_markdown": summary_markdown,
                    "pdf_object_key": pdf_object_key,
                }
            )
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to create summary.")

    return first_row(response.data, error_message="Failed to create summary.")


async def update_summary_pdf_key(
    client: AsyncClient,
    *,
    summary_id: str,
    pdf_object_key: str,
) -> dict[str, Any]:
    """Update the PDF object key for a summary."""
    try:
        response = (
            await client.table("summaries").update({"pdf_object_key": pdf_object_key}).eq("id", summary_id).execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to update summary PDF key.")

    return first_row(response.data, error_message="Failed to update summary PDF key.")

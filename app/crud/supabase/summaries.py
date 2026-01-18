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
            .select("id,summary_markdown,pdf_object_key")
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

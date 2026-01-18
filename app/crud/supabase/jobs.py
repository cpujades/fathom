"""Supabase jobs CRUD."""

from __future__ import annotations

from typing import Any

from postgrest import APIError

from app.services.supabase.helpers import first_row, raise_for_postgrest_error
from supabase import AsyncClient


async def create_job(client: AsyncClient, *, url: str, user_id: str) -> dict[str, Any]:
    """Insert a new job row and return it."""
    try:
        response = await client.table("jobs").insert({"url": url, "user_id": user_id}).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to create job.")

    return first_row(response.data, error_message="Failed to create job.")


async def fetch_job(client: AsyncClient, job_id: str) -> dict[str, Any]:
    """Fetch a job by ID."""
    try:
        response = await (
            client.table("jobs")
            .select("id,status,summary_id,error_code,error_message")
            .eq("id", job_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch job.")

    return first_row(
        response.data,
        error_message="Supabase returned an unexpected jobs shape.",
        not_found_message="Job not found.",
    )

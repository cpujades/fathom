"""Supabase jobs CRUD."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from postgrest import APIError

from fathom.services.supabase.helpers import first_row, raise_for_postgrest_error
from supabase import AsyncClient


async def create_job(client: AsyncClient, *, url: str, user_id: str) -> dict[str, Any]:
    """Insert a new job row and return it."""
    try:
        response = (
            await client.table("jobs")
            .insert(
                {
                    "url": url,
                    "user_id": user_id,
                    "stage": "queued",
                    "progress": 5,
                    "status_message": "Queued — waiting for a worker",
                }
            )
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to create job.")

    return first_row(response.data, error_message="Failed to create job.")


async def fetch_job(client: AsyncClient, job_id: str) -> dict[str, Any]:
    """Fetch a job by ID."""
    try:
        response = await (
            client.table("jobs")
            .select("id,status,summary_id,error_code,error_message,stage,progress,status_message")
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


async def claim_next_job(client: AsyncClient) -> dict[str, Any] | None:
    try:
        response = await client.rpc("claim_next_job").execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to claim job.")

    data = response.data
    if not data:
        return None
    if isinstance(data, dict):
        row = dict(data)
        # Supabase can return a "null composite" row when no job is available,
        # which appears as a dict with all fields set to None.
        if not row.get("id"):
            return None
        return row

    row = first_row(data, error_message="Supabase returned an unexpected claim shape.")
    if not row.get("id"):
        return None
    return row


async def requeue_stale_jobs(client: AsyncClient, *, stale_after_seconds: int) -> int:
    try:
        response = await client.rpc(
            "requeue_stale_jobs",
            {"stale_after": f"{stale_after_seconds} seconds"},
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to requeue stale jobs.")

    data = response.data
    if isinstance(data, int):
        return data
    if isinstance(data, dict) and "requeue_stale_jobs" in data:
        value = data.get("requeue_stale_jobs")
        if isinstance(value, int):
            return value
    return 0


async def mark_job_succeeded(client: AsyncClient, *, job_id: str, summary_id: str) -> None:
    try:
        await (
            client.table("jobs")
            .update(
                {
                    "status": "succeeded",
                    "stage": "completed",
                    "progress": 100,
                    "status_message": "Summary ready",
                    "summary_id": summary_id,
                    "error_code": None,
                    "error_message": None,
                    "last_error_at": None,
                    "run_after": None,
                }
            )
            .eq("id", job_id)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to update job status.")


async def mark_job_failed(
    client: AsyncClient,
    *,
    job_id: str,
    error_code: str,
    error_message: str,
) -> None:
    last_error_at = datetime.now(UTC).isoformat()
    try:
        await (
            client.table("jobs")
            .update(
                {
                    "status": "failed",
                    "stage": "failed",
                    "progress": 100,
                    "status_message": "Summary failed",
                    "error_code": error_code,
                    "error_message": error_message,
                    "last_error_at": last_error_at,
                    "run_after": None,
                }
            )
            .eq("id", job_id)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to update job status.")


async def mark_job_retry(
    client: AsyncClient,
    *,
    job_id: str,
    error_code: str,
    error_message: str,
    run_after: datetime,
) -> None:
    last_error_at = datetime.now(UTC).isoformat()
    try:
        await (
            client.table("jobs")
            .update(
                {
                    "status": "queued",
                    "stage": "queued",
                    "progress": 5,
                    "status_message": "Queued for retry",
                    "error_code": error_code,
                    "error_message": error_message,
                    "last_error_at": last_error_at,
                    "run_after": run_after.isoformat(),
                }
            )
            .eq("id", job_id)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to update job status.")


async def update_job_progress(
    client: AsyncClient,
    *,
    job_id: str,
    stage: str | None = None,
    progress: int | None = None,
    status_message: str | None = None,
    summary_id: str | None = None,
) -> None:
    payload: dict[str, Any] = {}
    if stage is not None:
        payload["stage"] = stage
    if progress is not None:
        payload["progress"] = progress
    if status_message is not None:
        payload["status_message"] = status_message
    if summary_id is not None:
        payload["summary_id"] = summary_id

    if not payload:
        return

    try:
        await client.table("jobs").update(payload).eq("id", job_id).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to update job progress.")

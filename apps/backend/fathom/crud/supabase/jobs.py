"""Supabase jobs CRUD."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from postgrest import APIError
from postgrest.types import CountMethod

from fathom.core.errors import ExternalServiceError, UsageSettlementError
from fathom.services.supabase.helpers import first_row, raise_for_postgrest_error
from supabase import AsyncClient


class JobLeaseLostError(RuntimeError):
    """The worker no longer owns the current attempt for a job."""


JobResolutionType = Literal["new", "joined_existing", "reused_ready"]


@dataclass(frozen=True)
class JobCreateResolution:
    """Race-safe result from the server job-creation command."""

    job: dict[str, Any]
    resolution_type: JobResolutionType


async def create_or_reuse_job(
    client: AsyncClient,
    *,
    url: str,
    source_key: str,
    user_id: str,
    duration_seconds: int | None = None,
    summary_id: str | None = None,
    cached_lease_seconds: int = 120,
) -> JobCreateResolution:
    """Create, join, or reuse a job atomically for one user and source."""
    params: dict[str, Any] = {
        "p_user_id": user_id,
        "p_url": url,
        "p_source_key": source_key,
        "p_duration_seconds": duration_seconds,
        "p_summary_id": summary_id,
        "p_cached_lease_for": f"{cached_lease_seconds} seconds",
    }

    try:
        response = await client.rpc("create_or_reuse_settled_job", params).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to create or reuse job.")

    data = response.data
    if isinstance(data, Mapping):
        result = dict(data)
    else:
        result = first_row(data, error_message="Supabase returned an unexpected job resolution shape.")

    resolution_type = result.get("resolution_type")
    job = result.get("job")
    if resolution_type not in {"new", "joined_existing", "reused_ready"} or not isinstance(job, Mapping):
        raise ExternalServiceError("Supabase returned an unexpected job resolution shape.")

    return JobCreateResolution(job=dict(job), resolution_type=resolution_type)


async def fetch_job(client: AsyncClient, job_id: str) -> dict[str, Any]:
    """Fetch a job by ID."""
    try:
        response = await (
            client.table("jobs")
            .select("id,status,url,summary_id,error_code,error_message,stage,progress,status_message,duration_seconds")
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


async def fetch_active_job_for_source(
    client: AsyncClient,
    *,
    user_id: str,
    source_key: str,
) -> dict[str, Any] | None:
    try:
        response = await (
            client.table("jobs")
            .select("id,status,url,summary_id,error_code,error_message,stage,progress,status_message,duration_seconds")
            .eq("user_id", user_id)
            .eq("source_key", source_key)
            .in_("status", ["queued", "running"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch active job.")

    data = response.data or []
    if not data:
        return None

    return first_row(data, error_message="Supabase returned an unexpected jobs shape.")


async def fetch_reusable_job_for_source(
    client: AsyncClient,
    *,
    user_id: str,
    source_key: str,
) -> dict[str, Any] | None:
    try:
        response = await (
            client.table("jobs")
            .select("id,status,url,summary_id,error_code,error_message,stage,progress,status_message,duration_seconds")
            .eq("user_id", user_id)
            .eq("source_key", source_key)
            .in_("status", ["succeeded", "deleted"])
            .not_.is_("summary_id", "null")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch reusable job.")

    data = response.data or []
    if not data:
        return None

    return first_row(data, error_message="Supabase returned an unexpected jobs shape.")


async def fetch_jobs_by_ids(client: AsyncClient, job_ids: list[str]) -> list[dict[str, Any]]:
    if not job_ids:
        return []

    try:
        response = await client.table("jobs").select("id,summary_id,status").in_("id", job_ids).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch jobs.")

    data = response.data or []
    return [row for row in data if isinstance(row, dict)]


async def fetch_briefing_jobs_page(
    client: AsyncClient,
    *,
    user_id: str,
    limit: int,
    offset: int,
    sort_desc: bool,
) -> tuple[list[dict[str, Any]], int]:
    try:
        response = await (
            client.table("jobs")
            .select("id,summary_id,status,url,created_at,duration_seconds,stage,progress", count=CountMethod.exact)
            .eq("user_id", user_id)
            .in_("status", ["queued", "running", "succeeded", "failed"])
            .order("created_at", desc=sort_desc)
            .range(offset, max(offset + limit - 1, offset))
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch briefing jobs.")

    data = response.data or []
    count = response.count if isinstance(response.count, int) else len(data)
    return [row for row in data if isinstance(row, dict)], count


async def claim_next_job(client: AsyncClient, *, lease_seconds: int) -> dict[str, Any] | None:
    try:
        response = await client.rpc(
            "claim_next_settled_job",
            {"p_lease_for": f"{lease_seconds} seconds"},
        ).execute()
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


async def renew_job_lease(
    client: AsyncClient,
    *,
    job_id: str,
    lease_token: str,
    lease_seconds: int,
) -> bool:
    try:
        response = await client.rpc(
            "renew_job_lease",
            {
                "p_job_id": job_id,
                "p_lease_token": lease_token,
                "p_lease_for": f"{lease_seconds} seconds",
            },
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to renew job lease.")

    return response.data is True


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


async def requeue_unsettled_jobs(client: AsyncClient) -> int:
    """Recover settlement-required jobs that were incorrectly made terminal."""
    try:
        response = await client.rpc("requeue_unsettled_jobs").execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to reconcile unsettled jobs.")

    data = response.data
    if isinstance(data, int):
        return data
    if isinstance(data, dict) and "requeue_unsettled_jobs" in data:
        value = data.get("requeue_unsettled_jobs")
        if isinstance(value, int):
            return value
    return 0


async def mark_job_succeeded(
    client: AsyncClient,
    *,
    job_id: str,
    summary_id: str,
    lease_token: str,
) -> None:
    try:
        response = await client.rpc(
            "complete_job_after_settlement",
            {
                "p_job_id": job_id,
                "p_summary_id": summary_id,
                "p_lease_token": lease_token,
            },
        ).execute()
    except APIError as exc:
        try:
            raise_for_postgrest_error(exc, "Failed to finalize settled job.")
        except ExternalServiceError as converted:
            raise UsageSettlementError(
                "Usage settlement completion could not be confirmed; retrying shortly."
            ) from converted

    if response.data is not True:
        raise JobLeaseLostError(f"Job lease lost or usage settlement missing for {job_id}.")


async def mark_job_failed(
    client: AsyncClient,
    *,
    job_id: str,
    lease_token: str,
    error_code: str,
    error_message: str,
) -> None:
    last_error_at = datetime.now(UTC).isoformat()
    await _update_job(
        client,
        job_id=job_id,
        lease_token=lease_token,
        payload={
            "status": "failed",
            "stage": "failed",
            "progress": 100,
            "status_message": "Summary failed",
            "error_code": error_code,
            "error_message": error_message,
            "last_error_at": last_error_at,
            "run_after": None,
            "claimed_at": None,
            "heartbeat_at": None,
            "lease_token": None,
            "lease_expires_at": None,
        },
        error_message="Failed to update job status.",
    )


async def mark_job_retry(
    client: AsyncClient,
    *,
    job_id: str,
    lease_token: str,
    error_code: str,
    error_message: str,
    run_after: datetime,
) -> None:
    last_error_at = datetime.now(UTC).isoformat()
    await _update_job(
        client,
        job_id=job_id,
        lease_token=lease_token,
        payload={
            "status": "queued",
            "stage": "queued",
            "progress": 5,
            "status_message": "Queued for retry",
            "error_code": error_code,
            "error_message": error_message,
            "last_error_at": last_error_at,
            "run_after": run_after.isoformat(),
            "claimed_at": None,
            "heartbeat_at": None,
            "lease_token": None,
            "lease_expires_at": None,
        },
        error_message="Failed to update job status.",
    )


async def mark_job_finalization_retry(
    client: AsyncClient,
    *,
    job_id: str,
    lease_token: str,
    error_code: str,
    error_message: str,
    run_after: datetime,
) -> None:
    """Release a failed settlement attempt without hiding the finalization state."""
    last_error_at = datetime.now(UTC).isoformat()
    await _update_job(
        client,
        job_id=job_id,
        lease_token=lease_token,
        payload={
            "status": "queued",
            "stage": "finalizing",
            "progress": 98,
            "status_message": "Finalizing your briefing; retrying shortly",
            "error_code": error_code,
            "error_message": error_message,
            "last_error_at": last_error_at,
            "run_after": run_after.isoformat(),
            "claimed_at": None,
            "heartbeat_at": None,
            "lease_token": None,
            "lease_expires_at": None,
        },
        error_message="Failed to queue job finalization retry.",
    )


async def update_job_progress(
    client: AsyncClient,
    *,
    job_id: str,
    lease_token: str,
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

    await _update_job(
        client,
        job_id=job_id,
        lease_token=lease_token,
        payload=payload,
        error_message="Failed to update job progress.",
    )


async def _update_job(
    client: AsyncClient,
    *,
    job_id: str,
    lease_token: str | None,
    payload: dict[str, Any],
    error_message: str,
) -> None:
    try:
        query = client.table("jobs").update(payload).eq("id", job_id)
        if lease_token is not None:
            query = query.eq("status", "running").eq("lease_token", lease_token)
        response = await query.execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, error_message)

    if lease_token is not None and not response.data:
        raise JobLeaseLostError(f"Job lease lost for {job_id}.")


async def archive_job(client: AsyncClient, *, job_id: str) -> None:
    try:
        await (
            client.table("jobs")
            .update(
                {
                    "status": "deleted",
                    "stage": "deleted",
                    "progress": 100,
                    "status_message": "Briefing removed from history",
                }
            )
            .eq("id", job_id)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to archive job.")


async def restore_job(client: AsyncClient, *, job_id: str) -> None:
    try:
        await (
            client.table("jobs")
            .update(
                {
                    "status": "succeeded",
                    "stage": "completed",
                    "progress": 100,
                    "status_message": "Using an existing briefing",
                }
            )
            .eq("id", job_id)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to restore job.")

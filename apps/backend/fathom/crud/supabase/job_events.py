"""Supabase job event CRUD."""

from __future__ import annotations

import logging
from typing import Any

from postgrest import APIError

from fathom.services.supabase.helpers import raise_for_postgrest_error
from supabase import AsyncClient


async def record_job_event(
    client: AsyncClient,
    *,
    job_id: str,
    event_type: str,
    stage: str | None = None,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "job_id": job_id,
        "event_type": event_type,
        "metadata": metadata or {},
    }
    if stage is not None:
        payload["stage"] = stage
    if message is not None:
        payload["message"] = message

    try:
        await client.table("job_events").insert(payload).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to record job event.")


async def record_job_event_best_effort(
    client: AsyncClient,
    logger: logging.Logger,
    *,
    job_id: str,
    event_type: str,
    stage: str | None = None,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        await record_job_event(
            client,
            job_id=job_id,
            event_type=event_type,
            stage=stage,
            message=message,
            metadata=metadata,
        )
    except Exception:
        logger.debug(
            "job_event.record_failed",
            extra={"job_id": job_id, "event_type": event_type},
            exc_info=True,
        )


async def list_job_events(client: AsyncClient, *, job_id: str) -> list[dict[str, Any]]:
    try:
        response = (
            await client.table("job_events")
            .select("id,job_id,event_type,stage,message,metadata,created_at")
            .eq("job_id", job_id)
            .order("created_at", desc=False)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch job events.")

    data = response.data or []
    return [row for row in data if isinstance(row, dict)]

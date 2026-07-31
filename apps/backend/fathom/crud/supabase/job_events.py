"""Supabase job event CRUD."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

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
    event_id: str | None = None,
) -> str:
    stable_event_id = event_id or str(uuid4())
    payload: dict[str, Any] = {
        "id": stable_event_id,
        "job_id": job_id,
        "event_type": event_type,
        "metadata": metadata or {},
    }
    if stage is not None:
        payload["stage"] = stage
    if message is not None:
        payload["message"] = message

    try:
        await (
            client.table("job_events")
            .upsert(
                payload,
                on_conflict="id",
                ignore_duplicates=True,
            )
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to record job event.")
    return stable_event_id


async def record_job_event_best_effort(
    client: AsyncClient,
    logger: logging.Logger,
    *,
    job_id: str,
    event_type: str,
    stage: str | None = None,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
    max_attempts: int = 3,
) -> bool:
    event_id = str(uuid4())
    bounded_attempts = max(1, min(max_attempts, 5))
    for attempt in range(1, bounded_attempts + 1):
        try:
            await record_job_event(
                client,
                job_id=job_id,
                event_type=event_type,
                stage=stage,
                message=message,
                metadata=metadata,
                event_id=event_id,
            )
            return True
        except Exception:
            if attempt == bounded_attempts:
                logger.error(
                    "job_event.record_failed",
                    extra={
                        "job_id": job_id,
                        "event_type": event_type,
                        "attempt": attempt,
                        "max_attempts": bounded_attempts,
                    },
                    exc_info=True,
                )
                return False
            logger.warning(
                "job_event.record_retrying",
                extra={
                    "job_id": job_id,
                    "event_type": event_type,
                    "attempt": attempt,
                    "max_attempts": bounded_attempts,
                },
            )
            await asyncio.sleep(0.05 * (2 ** (attempt - 1)))
    return False


async def list_job_events(client: AsyncClient, *, job_id: str) -> list[dict[str, Any]]:
    try:
        response = (
            await client.table("job_events")
            .select("id,sequence_id,job_id,event_type,stage,message,metadata,created_at")
            .eq("job_id", job_id)
            .order("sequence_id", desc=False)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch job events.")

    data = response.data or []
    return [row for row in data if isinstance(row, dict)]


async def list_job_events_after(
    client: AsyncClient,
    *,
    job_id: str,
    after_sequence_id: int,
    limit: int,
) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(limit, 100))
    try:
        response = (
            await client.table("job_events")
            .select("id,sequence_id,event_type,stage,message,metadata,created_at")
            .eq("job_id", job_id)
            .gt("sequence_id", max(after_sequence_id, 0))
            .order("sequence_id", desc=False)
            .limit(bounded_limit)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to replay job events.")

    data = response.data or []
    return [row for row in data if isinstance(row, dict)]


async def fetch_latest_job_event_sequence(client: AsyncClient, *, job_id: str) -> int:
    try:
        response = (
            await client.table("job_events")
            .select("sequence_id")
            .eq("job_id", job_id)
            .order("sequence_id", desc=True)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch the latest job event cursor.")

    data = response.data or []
    if not data or not isinstance(data[0], dict):
        return 0
    sequence_id = data[0].get("sequence_id")
    return sequence_id if isinstance(sequence_id, int) and sequence_id > 0 else 0

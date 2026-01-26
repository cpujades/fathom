from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import Request

from app.api.deps.auth import AuthContext
from app.core.config import Settings
from app.crud.supabase.jobs import fetch_job
from app.schemas.jobs import JobStatusResponse
from app.services.supabase import create_supabase_user_client


async def get_job_status(job_id: UUID, auth: AuthContext, settings: Settings) -> JobStatusResponse:
    client = await create_supabase_user_client(settings, auth.access_token)
    job = await fetch_job(client, str(job_id))

    return JobStatusResponse(
        job_id=job["id"],
        status=job["status"],
        summary_id=job.get("summary_id"),
        error_code=job.get("error_code"),
        error_message=job.get("error_message"),
    )


async def stream_job_status(
    job_id: UUID,
    auth: AuthContext,
    settings: Settings,
    *,
    poll_interval_seconds: float,
) -> AsyncIterator[JobStatusResponse]:
    client = await create_supabase_user_client(settings, auth.access_token)
    last_payload: dict[str, object] | None = None
    poll_interval = max(poll_interval_seconds, 1)

    while True:
        job = await fetch_job(client, str(job_id))
        response = JobStatusResponse(
            job_id=job["id"],
            status=job["status"],
            summary_id=job.get("summary_id"),
            error_code=job.get("error_code"),
            error_message=job.get("error_message"),
        )

        payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()
        if payload != last_payload:
            yield response
            last_payload = payload

        if response.status in ("succeeded", "failed"):
            break

        await asyncio.sleep(poll_interval)


async def stream_job_events(
    job_id: UUID,
    request: Request,
    auth: AuthContext,
    settings: Settings,
    *,
    poll_interval_seconds: float,
) -> AsyncIterator[str]:
    async for status in stream_job_status(
        job_id,
        auth,
        settings,
        poll_interval_seconds=poll_interval_seconds,
    ):
        if await request.is_disconnected():
            break
        payload = status.model_dump() if hasattr(status, "model_dump") else status.dict()
        yield f"event: job\ndata: {json.dumps(payload)}\n\n"

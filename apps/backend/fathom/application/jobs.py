from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import Request

from fathom.api.deps.auth import AuthContext
from fathom.core.config import Settings
from fathom.core.logging import log_context
from fathom.crud.supabase.jobs import fetch_job
from fathom.schemas.jobs import JobStatusResponse
from fathom.services.supabase import create_supabase_user_client

# SSE polling interval for job status updates
JOB_STATUS_POLL_INTERVAL_SECONDS = 1

logger = logging.getLogger(__name__)


async def get_job_status(job_id: UUID, auth: AuthContext, settings: Settings) -> JobStatusResponse:
    job_id_str = str(job_id)
    with log_context(job_id=job_id_str, user_id=auth.user_id):
        client = await create_supabase_user_client(settings, auth.access_token)
        job = await fetch_job(client, job_id_str)
        status = job["status"]
        logger.info("job status fetched", extra={"status": status, "summary_id": job.get("summary_id")})

        return JobStatusResponse(
            job_id=job["id"],
            status=status,
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
    job_id_str = str(job_id)
    with log_context(job_id=job_id_str, user_id=auth.user_id):
        client = await create_supabase_user_client(settings, auth.access_token)
        last_payload: dict[str, object] | None = None
        poll_interval = max(poll_interval_seconds, 1)

        while True:
            job = await fetch_job(client, job_id_str)
            response = JobStatusResponse(
                job_id=job["id"],
                status=job["status"],
                summary_id=job.get("summary_id"),
                error_code=job.get("error_code"),
                error_message=job.get("error_message"),
            )

            payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()
            if payload != last_payload:
                logger.info(
                    "job status update",
                    extra={"status": response.status, "summary_id": response.summary_id},
                )
                yield response
                last_payload = payload

            if response.status in ("succeeded", "failed"):
                logger.info("job terminal state reached", extra={"status": response.status})
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
    job_id_str = str(job_id)
    with log_context(job_id=job_id_str, user_id=auth.user_id):
        async for status in stream_job_status(
            job_id,
            auth,
            settings,
            poll_interval_seconds=poll_interval_seconds,
        ):
            if await request.is_disconnected():
                logger.info("job events stream disconnected by client")
                break
            payload = status.model_dump() if hasattr(status, "model_dump") else status.dict()
            yield f"event: job\ndata: {json.dumps(payload)}\n\n"

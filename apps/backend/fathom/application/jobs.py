from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import Request
from fastapi.encoders import jsonable_encoder

from fathom.api.deps.auth import AuthContext
from fathom.core.config import Settings
from fathom.core.logging import log_context
from fathom.crud.supabase.jobs import fetch_job
from fathom.crud.supabase.summaries import fetch_summary
from fathom.schemas.jobs import JobStatusResponse
from fathom.services.supabase import create_supabase_user_client
from fathom.services.supabase.postgres import listen_to_job_updates

# SSE polling interval for job status updates (used as fallback)
JOB_STATUS_POLL_INTERVAL_SECONDS = 2

# Optimized polling interval for fallback mode
FALLBACK_POLL_INTERVAL_SECONDS = 10

# Heartbeat interval for keeping SSE connection alive
HEARTBEAT_INTERVAL_SECONDS = 15

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
            stage=job.get("stage"),
            progress=job.get("progress"),
            status_message=job.get("status_message"),
        )


async def stream_job_status_realtime(
    job_id: UUID,
    auth: AuthContext,
    settings: Settings,
    *,
    heartbeat_interval_seconds: float,
) -> AsyncIterator[JobStatusResponse]:
    """Stream job status using Postgres LISTEN/NOTIFY.

    This is the efficient, event-driven approach that only queries
    the database when actual changes occur.
    """
    job_id_str = str(job_id)
    client = await create_supabase_user_client(settings, auth.access_token)
    last_payload: dict[str, object] | None = None

    # Fetch initial status
    job = await fetch_job(client, job_id_str)
    response = JobStatusResponse(
        job_id=job["id"],
        status=job["status"],
        summary_id=job.get("summary_id"),
        error_code=job.get("error_code"),
        error_message=job.get("error_message"),
        stage=job.get("stage"),
        progress=job.get("progress"),
        status_message=job.get("status_message"),
    )

    payload = jsonable_encoder(response)
    last_payload = payload
    yield response

    # Check if already in terminal state
    if response.status in ("succeeded", "failed"):
        with log_context(job_id=job_id_str, user_id=auth.user_id):
            logger.info("job already in terminal state", extra={"status": response.status})
        return

    # Listen for updates
    try:
        async for notification in listen_to_job_updates(
            settings,
            job_id_str,
            timeout_seconds=heartbeat_interval_seconds,
        ):
            # Empty notification means heartbeat (timeout without updates)
            if not notification:
                continue

            # Fetch updated job status
            job = await fetch_job(client, job_id_str)
            response = JobStatusResponse(
                job_id=job["id"],
                status=job["status"],
                summary_id=job.get("summary_id"),
                error_code=job.get("error_code"),
                error_message=job.get("error_message"),
                stage=job.get("stage"),
                progress=job.get("progress"),
                status_message=job.get("status_message"),
            )

            payload = jsonable_encoder(response)
            if payload != last_payload:
                with log_context(job_id=job_id_str, user_id=auth.user_id):
                    logger.info(
                        "job status update (realtime)",
                        extra={"status": response.status, "summary_id": response.summary_id},
                    )
                yield response
                last_payload = payload

            if response.status in ("succeeded", "failed"):
                with log_context(job_id=job_id_str, user_id=auth.user_id):
                    logger.info("job terminal state reached (realtime)", extra={"status": response.status})
                break
    except Exception as exc:
        # Log error and let caller handle fallback
        with log_context(job_id=job_id_str, user_id=auth.user_id):
            logger.warning("realtime streaming failed, caller should use fallback", exc_info=exc)
        raise


async def stream_job_status_polling(
    job_id: UUID,
    auth: AuthContext,
    settings: Settings,
    *,
    poll_interval_seconds: float,
) -> AsyncIterator[JobStatusResponse]:
    """Stream job status using polling (fallback mode).

    This polls the database at regular intervals. Less efficient but
    reliable when LISTEN/NOTIFY is unavailable.
    """
    job_id_str = str(job_id)
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
            stage=job.get("stage"),
            progress=job.get("progress"),
            status_message=job.get("status_message"),
        )

        payload = jsonable_encoder(response)
        if payload != last_payload:
            with log_context(job_id=job_id_str, user_id=auth.user_id):
                logger.info(
                    "job status update (polling)",
                    extra={"status": response.status, "summary_id": response.summary_id},
                )
            yield response
            last_payload = payload

        if response.status in ("succeeded", "failed"):
            with log_context(job_id=job_id_str, user_id=auth.user_id):
                logger.info("job terminal state reached (polling)", extra={"status": response.status})
            break

        await asyncio.sleep(poll_interval)


async def stream_job_status(
    job_id: UUID,
    auth: AuthContext,
    settings: Settings,
    *,
    poll_interval_seconds: float,
) -> AsyncIterator[JobStatusResponse]:
    """Stream job status with automatic fallback to polling.

    Tries to use LISTEN/NOTIFY first, falls back to polling if that fails.
    """
    job_id_str = str(job_id)

    try:
        # Try realtime first
        with log_context(job_id=job_id_str, user_id=auth.user_id):
            logger.info("attempting realtime job status streaming")

        async for status in stream_job_status_realtime(
            job_id,
            auth,
            settings,
            heartbeat_interval_seconds=HEARTBEAT_INTERVAL_SECONDS,
        ):
            yield status
    except Exception as exc:
        # Fall back to polling
        with log_context(job_id=job_id_str, user_id=auth.user_id):
            logger.warning(
                "realtime streaming failed, falling back to polling",
                extra={"error": str(exc)},
            )

        async for status in stream_job_status_polling(
            job_id,
            auth,
            settings,
            poll_interval_seconds=FALLBACK_POLL_INTERVAL_SECONDS,
        ):
            yield status


async def stream_job_events(
    job_id: UUID,
    request: Request,
    auth: AuthContext,
    settings: Settings,
    *,
    poll_interval_seconds: float,
) -> AsyncIterator[str]:
    job_id_str = str(job_id)
    client = await create_supabase_user_client(settings, auth.access_token)
    last_summary_text = ""

    async for status in stream_job_status(
        job_id,
        auth,
        settings,
        poll_interval_seconds=poll_interval_seconds,
    ):
        if await request.is_disconnected():
            with log_context(job_id=job_id_str, user_id=auth.user_id):
                logger.info("job events stream disconnected by client")
            break
        payload = jsonable_encoder(status)
        yield f"event: job\ndata: {json.dumps(payload)}\n\n"

        if status.summary_id and status.stage in {"summarizing", "rendering", "completed"}:
            try:
                summary = await fetch_summary(client, str(status.summary_id))
            except Exception:
                continue

            summary_text = summary.get("summary_markdown") or ""
            if summary_text and summary_text != last_summary_text:
                if summary_text.startswith(last_summary_text):
                    delta = summary_text[len(last_summary_text) :]
                    data = {"delta": delta}
                else:
                    data = {"markdown": summary_text}
                yield f"event: summary\ndata: {json.dumps(data)}\n\n"
                last_summary_text = summary_text

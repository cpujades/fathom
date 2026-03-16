from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import Request
from starlette.responses import StreamingResponse

from fathom.api.deps.auth import AuthContext
from fathom.application.briefing_contract import (
    NormalizedSource,
    build_briefing_session_snapshot,
    encode_sse_event,
    normalize_source,
)
from fathom.application.guards import validate_video_duration, validate_youtube_url
from fathom.application.usage import ensure_usage_allowed, record_usage_for_job
from fathom.core.config import Settings
from fathom.core.constants import SUMMARY_PROMPT_KEY_DEFAULT
from fathom.core.logging import log_context
from fathom.crud.supabase.jobs import (
    create_job,
    fetch_active_job_for_source,
    fetch_completed_job_for_source,
    fetch_job,
    mark_job_succeeded,
    update_job_progress,
)
from fathom.crud.supabase.summaries import fetch_summary, fetch_summary_by_keys
from fathom.crud.supabase.transcripts import fetch_transcript_by_hash, fetch_transcript_by_video_id
from fathom.schemas.briefing_sessions import (
    BriefingSessionCreateRequest,
    BriefingSessionResolution,
    BriefingSessionResponse,
)
from fathom.services.downloader import fetch_video_metadata
from fathom.services.summarizer import OPENROUTER_MODEL
from fathom.services.supabase import (
    create_supabase_admin_client,
    create_supabase_user_client,
    listen_for_notifications,
)

logger = logging.getLogger(__name__)

KEEPALIVE_SECONDS = 15.0
GROQ_PROVIDER_MODEL = "groq:whisper-large-v3-turbo"


async def create_briefing_session(
    request: BriefingSessionCreateRequest,
    auth: AuthContext,
    settings: Settings,
) -> BriefingSessionResponse:
    submitted_url = str(request.url)
    with log_context(user_id=auth.user_id):
        logger.info("briefing session request start")
        validate_youtube_url(submitted_url)
        source = normalize_source(submitted_url)
        user_client = await create_supabase_user_client(settings, auth.access_token)

        active_job = await fetch_active_job_for_source(
            user_client,
            user_id=auth.user_id,
            url=source.canonical_url,
        )
        if active_job:
            logger.info("briefing session joined existing work", extra={"session_id": active_job["id"]})
            return await _build_session_snapshot(
                user_client=user_client,
                job=active_job,
                source=source,
                resolution_type="joined_existing",
            )

        completed_job = await fetch_completed_job_for_source(
            user_client,
            user_id=auth.user_id,
            url=source.canonical_url,
        )
        if completed_job:
            logger.info("briefing session reused user's existing briefing", extra={"session_id": completed_job["id"]})
            return await _build_session_snapshot(
                user_client=user_client,
                job=completed_job,
                source=source,
                resolution_type="reused_ready",
            )

        metadata = await asyncio.to_thread(fetch_video_metadata, source.canonical_url)
        validate_video_duration(metadata.duration_seconds)
        logger.info(
            "source metadata validated",
            extra={"video_id": metadata.video_id, "duration_seconds": metadata.duration_seconds},
        )

        await ensure_usage_allowed(
            user_id=auth.user_id,
            duration_seconds=metadata.duration_seconds,
            settings=settings,
        )

        admin_client = await create_supabase_admin_client(settings)
        cached_summary = await _find_ready_cached_summary(admin_client, source)
        if cached_summary:
            ready_job = await _create_ready_reused_session(
                user_id=auth.user_id,
                source=source,
                duration_seconds=metadata.duration_seconds,
                summary_id=str(cached_summary["id"]),
                user_client=user_client,
                admin_client=admin_client,
                settings=settings,
            )
            logger.info("briefing session reused cached briefing", extra={"session_id": ready_job["id"]})
            return await _build_session_snapshot(
                user_client=user_client,
                job=ready_job,
                source=source,
                resolution_type="reused_ready",
            )

        created_job = await create_job(
            user_client,
            url=source.canonical_url,
            user_id=auth.user_id,
            duration_seconds=metadata.duration_seconds,
        )
        job = await fetch_job(user_client, str(created_job["id"]))
        logger.info("briefing session created", extra={"session_id": job["id"]})
        return await _build_session_snapshot(user_client=user_client, job=job, source=source, resolution_type="new")


async def get_briefing_session(session_id: UUID, auth: AuthContext, settings: Settings) -> BriefingSessionResponse:
    session_id_str = str(session_id)
    with log_context(user_id=auth.user_id, session_id=session_id_str):
        user_client = await create_supabase_user_client(settings, auth.access_token)
        job = await fetch_job(user_client, session_id_str)
        source = normalize_source(job["url"])
        logger.info("briefing session fetched", extra={"state": job.get("stage"), "status": job.get("status")})
        return await _build_session_snapshot(user_client=user_client, job=job, source=source)


async def stream_briefing_session_events(
    session_id: UUID,
    auth: AuthContext,
    settings: Settings,
    request: Request,
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        user_client = await create_supabase_user_client(settings, auth.access_token)
        session_id_str = str(session_id)
        job = await fetch_job(user_client, session_id_str)
        source = normalize_source(job["url"])
        snapshot = await _build_session_snapshot(user_client=user_client, job=job, source=source)
        yield "retry: 2000\n\n"
        yield encode_sse_event(
            event_type="session.snapshot",
            event_id="1",
            data=snapshot.model_dump(mode="json"),
        )

        if snapshot.state in {"ready", "failed"}:
            return

        current_signature = _snapshot_signature(snapshot)
        event_counter = 2

        async with listen_for_notifications(settings, "job_updates") as queue:
            while True:
                if await request.is_disconnected():
                    return

                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                if str(payload.get("id")) != session_id_str:
                    continue

                refreshed_job = await fetch_job(user_client, session_id_str)
                refreshed_source = normalize_source(refreshed_job["url"])
                refreshed_snapshot = await _build_session_snapshot(
                    user_client=user_client,
                    job=refreshed_job,
                    source=refreshed_source,
                )
                refreshed_signature = _snapshot_signature(refreshed_snapshot)
                if refreshed_signature == current_signature:
                    continue

                current_signature = refreshed_signature
                event_type = "session.updated"
                if refreshed_snapshot.state == "ready":
                    event_type = "session.ready"
                elif refreshed_snapshot.state == "failed":
                    event_type = "session.failed"

                yield encode_sse_event(
                    event_type=event_type,
                    event_id=str(event_counter),
                    data=refreshed_snapshot.model_dump(mode="json"),
                )
                event_counter += 1

                if refreshed_snapshot.state in {"ready", "failed"}:
                    return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _build_session_snapshot(
    *,
    user_client: Any,
    job: dict[str, Any],
    source: NormalizedSource,
    resolution_type: BriefingSessionResolution | None = None,
) -> BriefingSessionResponse:
    summary = await _fetch_summary_for_job(user_client, job)
    return build_briefing_session_snapshot(
        job=job,
        source=source,
        resolution_type=resolution_type,
        summary=summary,
    )


async def _fetch_summary_for_job(user_client: Any, job: dict[str, Any]) -> dict[str, Any] | None:
    summary_id = job.get("summary_id")
    if not summary_id:
        return None
    return await fetch_summary(user_client, str(summary_id))


async def _create_ready_reused_session(
    *,
    user_id: str,
    source: NormalizedSource,
    duration_seconds: int | None,
    summary_id: str,
    user_client: Any,
    admin_client: Any,
    settings: Settings,
) -> dict[str, Any]:
    created_job = await create_job(
        user_client,
        url=source.canonical_url,
        user_id=user_id,
        duration_seconds=duration_seconds,
    )
    session_id = str(created_job["id"])
    await update_job_progress(
        admin_client,
        job_id=session_id,
        stage="cached",
        progress=100,
        status_message="Using an existing briefing",
        summary_id=summary_id,
    )
    await mark_job_succeeded(admin_client, job_id=session_id, summary_id=summary_id)
    try:
        await record_usage_for_job(
            user_id=user_id,
            job_id=session_id,
            duration_seconds=duration_seconds,
            settings=settings,
        )
    except Exception:
        logger.exception("usage recording failed for reused briefing", extra={"session_id": session_id})
    return await fetch_job(user_client, session_id)


async def _find_ready_cached_summary(admin_client: Any, source: NormalizedSource) -> dict[str, Any] | None:
    transcript = None
    if source.video_id:
        transcript = await fetch_transcript_by_video_id(
            admin_client,
            video_id=source.video_id,
            provider_model=GROQ_PROVIDER_MODEL,
        )

    if not transcript:
        transcript = await fetch_transcript_by_hash(
            admin_client,
            url_hash=_hash_url(source.canonical_url),
            provider_model=GROQ_PROVIDER_MODEL,
        )

    if not transcript:
        return None

    summary = await fetch_summary_by_keys(
        admin_client,
        transcript_id=str(transcript["id"]),
        prompt_key=SUMMARY_PROMPT_KEY_DEFAULT,
        summary_model=OPENROUTER_MODEL,
    )
    if not summary:
        return None

    markdown = summary.get("summary_markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        return None

    return summary


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _snapshot_signature(snapshot: BriefingSessionResponse) -> tuple[Any, ...]:
    return (
        str(snapshot.session_id),
        str(snapshot.briefing_id) if snapshot.briefing_id else None,
        snapshot.state,
        snapshot.progress,
        snapshot.detail,
        snapshot.error_code,
        snapshot.error_message,
    )

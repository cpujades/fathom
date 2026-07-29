from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import Request
from starlette.responses import StreamingResponse

from fathom.api.deps.auth import AuthContext
from fathom.application.briefings.contract import (
    NormalizedSource,
    build_briefing_session_snapshot,
    encode_sse_event,
    normalize_source,
)
from fathom.application.guards import validate_video_duration, validate_youtube_url
from fathom.application.usage import ensure_usage_allowed, record_usage_for_job
from fathom.core.config import Settings
from fathom.core.constants import (
    SUMMARY_PROMPT_KEY_DEFAULT,
    SUMMARY_PROMPT_KEY_EVIDENCE,
)
from fathom.core.errors import NotFoundError, UsageSettlementError
from fathom.core.logging import log_context
from fathom.crud.supabase.job_events import (
    fetch_latest_job_event_sequence,
    list_job_events_after,
    record_job_event_best_effort,
)
from fathom.crud.supabase.jobs import (
    JobCreateResolution,
    JobLeaseLostError,
    archive_job,
    create_or_reuse_job,
    fetch_active_job_for_source,
    fetch_job,
    fetch_reusable_job_for_source,
    mark_job_finalization_retry,
    mark_job_succeeded,
    restore_job,
)
from fathom.crud.supabase.summaries import fetch_summary, fetch_summary_by_keys
from fathom.crud.supabase.transcripts import (
    fetch_transcript_by_hash,
    fetch_transcript_by_id,
    fetch_transcript_by_video_id,
    fetch_transcript_segments,
)
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
)

logger = logging.getLogger(__name__)

KEEPALIVE_SECONDS = 15.0
EVENT_POLL_SECONDS = 1.0
SNAPSHOT_RECONCILE_SECONDS = 10.0
EVENT_BATCH_LIMIT = 100
MAX_REPLAY_EVENTS = 500
GROQ_PROVIDER_MODEL = "groq:whisper-large-v3-turbo"


async def create_briefing_session(
    request: BriefingSessionCreateRequest,
    auth: AuthContext,
    settings: Settings,
) -> BriefingSessionResponse:
    submitted_url = str(request.url)
    with log_context(user_id=auth.user_id):
        logger.info("briefing_session.create.started")
        validate_youtube_url(submitted_url)
        source = normalize_source(submitted_url)
        user_client = await create_supabase_user_client(settings, auth.access_token)
        admin_client = await create_supabase_admin_client(settings)

        active_job = await fetch_active_job_for_source(
            user_client,
            user_id=auth.user_id,
            source_key=source.source_identity_key,
        )
        if active_job:
            logger.info("briefing_session.reused_active", extra={"session_id": active_job["id"]})
            return await _build_session_snapshot(
                user_client=user_client,
                admin_client=admin_client,
                job=active_job,
                source=source,
                resolution_type="joined_existing",
            )

        completed_job = await fetch_reusable_job_for_source(
            user_client,
            user_id=auth.user_id,
            source_key=source.source_identity_key,
        )
        if completed_job and not await _job_has_ready_summary(user_client, completed_job):
            logger.warning(
                "briefing_session.reusable_summary_not_ready",
                extra={"session_id": completed_job["id"]},
            )
            completed_job = None
        if completed_job:
            if str(completed_job.get("status") or "") == "deleted":
                await restore_job(admin_client, job_id=str(completed_job["id"]))
                restored_job = await fetch_job(user_client, str(completed_job["id"]))
                logger.info("briefing_session.restored_archived", extra={"session_id": restored_job["id"]})
                return await _build_session_snapshot(
                    user_client=user_client,
                    admin_client=admin_client,
                    job=restored_job,
                    source=source,
                    resolution_type="reused_ready",
                )
            logger.info("briefing_session.reused_ready", extra={"session_id": completed_job["id"]})
            return await _build_session_snapshot(
                user_client=user_client,
                admin_client=admin_client,
                job=completed_job,
                source=source,
                resolution_type="reused_ready",
            )

        metadata = await asyncio.to_thread(fetch_video_metadata, source.canonical_url)
        validate_video_duration(metadata.duration_seconds)
        logger.info(
            "briefing_session.source.validated",
            extra={"video_id": metadata.video_id, "duration_seconds": metadata.duration_seconds},
        )

        await ensure_usage_allowed(
            user_id=auth.user_id,
            duration_seconds=metadata.duration_seconds,
            settings=settings,
        )

        cached_summary = await _find_ready_cached_summary(admin_client, source)
        if cached_summary:
            cached_resolution = await _create_ready_reused_session(
                user_id=auth.user_id,
                source=source,
                duration_seconds=metadata.duration_seconds,
                summary_id=str(cached_summary["id"]),
                user_client=user_client,
                admin_client=admin_client,
                settings=settings,
            )
            ready_job = cached_resolution.job
            response_resolution: BriefingSessionResolution = cached_resolution.resolution_type
            if cached_resolution.resolution_type == "new":
                response_resolution = "reused_ready"
                await record_job_event_best_effort(
                    admin_client,
                    logger,
                    job_id=str(ready_job["id"]),
                    event_type="session_created",
                    stage="cached",
                    message="Ready session created from cached summary.",
                    metadata={
                        "resolution_type": response_resolution,
                        "video_id": metadata.video_id,
                        "duration_seconds": metadata.duration_seconds,
                        "summary_id": str(cached_summary["id"]),
                    },
                )
            logger.info(
                "briefing_session.reused_cached",
                extra={
                    "session_id": ready_job["id"],
                    "resolution_type": response_resolution,
                },
            )
            return await _build_session_snapshot(
                user_client=user_client,
                admin_client=admin_client,
                job=ready_job,
                source=source,
                resolution_type=response_resolution,
            )

        job_resolution = await create_or_reuse_job(
            admin_client,
            url=source.canonical_url,
            source_key=source.source_identity_key,
            user_id=auth.user_id,
            duration_seconds=metadata.duration_seconds,
        )
        job = await fetch_job(user_client, str(job_resolution.job["id"]))
        logger.info(
            "briefing_session.resolved",
            extra={
                "session_id": job["id"],
                "resolution_type": job_resolution.resolution_type,
            },
        )
        if job_resolution.resolution_type == "new":
            await record_job_event_best_effort(
                admin_client,
                logger,
                job_id=str(job["id"]),
                event_type="session_created",
                stage="queued",
                message="Briefing session created.",
                metadata={
                    "resolution_type": "new",
                    "video_id": metadata.video_id,
                    "duration_seconds": metadata.duration_seconds,
                },
            )
        return await _build_session_snapshot(
            user_client=user_client,
            admin_client=admin_client,
            job=job,
            source=source,
            resolution_type=job_resolution.resolution_type,
        )


async def get_briefing_session(session_id: UUID, auth: AuthContext, settings: Settings) -> BriefingSessionResponse:
    session_id_str = str(session_id)
    with log_context(user_id=auth.user_id, session_id=session_id_str):
        user_client = await create_supabase_user_client(settings, auth.access_token)
        admin_client = await create_supabase_admin_client(settings)
        job = await fetch_job(user_client, session_id_str)
        if str(job.get("status") or "") == "deleted":
            raise NotFoundError("Briefing session not found.")
        source = normalize_source(job["url"])
        logger.info("briefing_session.fetched", extra={"state": job.get("stage"), "status": job.get("status")})
        return await _build_session_snapshot(user_client=user_client, admin_client=admin_client, job=job, source=source)


async def stream_briefing_session_events(
    session_id: UUID,
    auth: AuthContext,
    settings: Settings,
    request: Request,
) -> StreamingResponse:
    return StreamingResponse(
        _session_event_stream(
            session_id=session_id,
            auth=auth,
            settings=settings,
            request=request,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _session_event_stream(
    *,
    session_id: UUID,
    auth: AuthContext,
    settings: Settings,
    request: Request,
) -> AsyncIterator[str]:
    user_client = await create_supabase_user_client(settings, auth.access_token)
    admin_client = await create_supabase_admin_client(settings)
    session_id_str = str(session_id)
    with log_context(user_id=auth.user_id, session_id=session_id_str):
        logger.info("briefing_session.stream.opened")

    job = await fetch_job(user_client, session_id_str)
    if str(job.get("status") or "") == "deleted":
        raise NotFoundError("Briefing session not found.")

    latest_sequence = await fetch_latest_job_event_sequence(user_client, job_id=session_id_str)
    requested_cursor = _parse_last_event_id(request.headers.get("last-event-id"))
    cursor = latest_sequence if requested_cursor is None else min(requested_cursor, latest_sequence)

    yield "retry: 2000\n\n"
    if requested_cursor is not None:
        replay_events, cursor = await _replay_session_events(
            user_client=user_client,
            session_id=session_id_str,
            cursor=cursor,
            latest_sequence=latest_sequence,
        )
        for replay_event in replay_events:
            yield replay_event

    snapshot = await _build_session_snapshot(
        user_client=user_client,
        admin_client=admin_client,
        job=job,
        source=normalize_source(job["url"]),
    )
    yield encode_sse_event(
        event_type="session.snapshot",
        event_id=str(cursor),
        data=snapshot.model_dump(mode="json"),
    )

    if snapshot.state in {"ready", "failed"}:
        _log_stream_closed(auth.user_id, session_id_str, snapshot.state)
        return

    current_signature = _snapshot_signature(snapshot)
    current_markdown = snapshot.briefing_markdown or ""
    seconds_since_snapshot = 0.0
    seconds_since_keepalive = 0.0

    while True:
        if await request.is_disconnected():
            with log_context(user_id=auth.user_id, session_id=session_id_str):
                logger.info("briefing_session.stream.disconnected")
            return

        await asyncio.sleep(EVENT_POLL_SECONDS)
        seconds_since_snapshot += EVENT_POLL_SECONDS
        seconds_since_keepalive += EVENT_POLL_SECONDS
        events = await list_job_events_after(
            user_client,
            job_id=session_id_str,
            after_sequence_id=cursor,
            limit=EVENT_BATCH_LIMIT,
        )
        for event in events:
            sequence_id = _event_sequence_id(event)
            if sequence_id is None:
                continue
            cursor = sequence_id
            yield _encode_replayed_event(event, sequence_id)

        if events or seconds_since_snapshot >= SNAPSHOT_RECONCILE_SECONDS:
            latest_sequence = await fetch_latest_job_event_sequence(user_client, job_id=session_id_str)
            cursor = max(cursor, latest_sequence)
            refreshed_job = await fetch_job(user_client, session_id_str)
            refreshed_snapshot = await _build_session_snapshot(
                user_client=user_client,
                admin_client=admin_client,
                job=refreshed_job,
                source=normalize_source(refreshed_job["url"]),
            )
            for encoded in _encode_snapshot_changes(
                previous_signature=current_signature,
                previous_markdown=current_markdown,
                snapshot=refreshed_snapshot,
                cursor=cursor,
            ):
                yield encoded

            current_signature = _snapshot_signature(refreshed_snapshot)
            current_markdown = refreshed_snapshot.briefing_markdown or ""
            seconds_since_snapshot = 0.0
            if refreshed_snapshot.state in {"ready", "failed"}:
                _log_stream_closed(auth.user_id, session_id_str, refreshed_snapshot.state)
                return

        if seconds_since_keepalive >= KEEPALIVE_SECONDS:
            yield ": keepalive\n\n"
            seconds_since_keepalive = 0.0


async def _replay_session_events(
    *,
    user_client: Any,
    session_id: str,
    cursor: int,
    latest_sequence: int,
) -> tuple[list[str], int]:
    encoded_events: list[str] = []
    replayed = 0
    while cursor < latest_sequence and replayed < MAX_REPLAY_EVENTS:
        previous_cursor = cursor
        events = await list_job_events_after(
            user_client,
            job_id=session_id,
            after_sequence_id=cursor,
            limit=min(EVENT_BATCH_LIMIT, MAX_REPLAY_EVENTS - replayed),
        )
        if not events:
            break
        for event in events:
            sequence_id = _event_sequence_id(event)
            if sequence_id is None:
                continue
            cursor = sequence_id
            replayed += 1
            encoded_events.append(_encode_replayed_event(event, sequence_id))
        if cursor == previous_cursor:
            break

    if cursor < latest_sequence:
        logger.warning(
            "briefing_session.stream.replay_truncated",
            extra={
                "session_id": session_id,
                "replayed_events": replayed,
                "latest_sequence_id": latest_sequence,
            },
        )
        cursor = latest_sequence
    return encoded_events, cursor


def _encode_snapshot_changes(
    *,
    previous_signature: tuple[Any, ...],
    previous_markdown: str,
    snapshot: BriefingSessionResponse,
    cursor: int,
) -> Iterator[str]:
    markdown = snapshot.briefing_markdown or ""
    signature = _snapshot_signature(snapshot)
    markdown_changed = markdown != previous_markdown

    if markdown_changed and markdown.startswith(previous_markdown):
        delta = markdown[len(previous_markdown) :]
        if delta:
            yield encode_sse_event(
                event_type="session.content_delta",
                event_id=str(cursor),
                data=_build_content_delta_event(snapshot, delta, len(markdown)),
            )
    elif snapshot.state in {"ready", "failed"} or markdown_changed:
        event_type = "session.updated"
        if snapshot.state == "ready":
            event_type = "session.ready"
        elif snapshot.state == "failed":
            event_type = "session.failed"
        yield encode_sse_event(
            event_type=event_type,
            event_id=str(cursor),
            data=snapshot.model_dump(mode="json"),
        )

    if signature != previous_signature and snapshot.state not in {"ready", "failed"}:
        yield encode_sse_event(
            event_type="session.status",
            event_id=str(cursor),
            data=_build_status_event(snapshot),
        )

    if snapshot.state in {"ready", "failed"}:
        yield encode_sse_event(
            event_type="session.snapshot",
            event_id=str(cursor),
            data=snapshot.model_dump(mode="json"),
        )


def _parse_last_event_id(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        cursor = int(value)
    except ValueError:
        return None
    return cursor if cursor >= 0 else None


def _event_sequence_id(event: dict[str, Any]) -> int | None:
    value = event.get("sequence_id")
    return value if isinstance(value, int) and value > 0 else None


def _encode_replayed_event(event: dict[str, Any], sequence_id: int) -> str:
    return encode_sse_event(
        event_type="session.event",
        event_id=str(sequence_id),
        data={
            "event_type": event.get("event_type"),
            "stage": event.get("stage"),
            "created_at": event.get("created_at"),
        },
    )


def _log_stream_closed(user_id: str, session_id: str, state: str) -> None:
    with log_context(user_id=user_id, session_id=session_id):
        logger.info("briefing_session.stream.closed", extra={"state": state})


async def _build_session_snapshot(
    *,
    user_client: Any,
    admin_client: Any,
    job: dict[str, Any],
    source: NormalizedSource,
    resolution_type: BriefingSessionResolution | None = None,
) -> BriefingSessionResponse:
    summary, transcript = await _fetch_summary_and_transcript_for_job(user_client, admin_client, job)
    return build_briefing_session_snapshot(
        job=job,
        source=source,
        resolution_type=resolution_type,
        summary=summary,
        transcript=transcript,
    )


async def _fetch_summary_and_transcript_for_job(
    user_client: Any,
    admin_client: Any,
    job: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    summary_id = job.get("summary_id")
    if not summary_id:
        return None, None

    summary = await fetch_summary(user_client, str(summary_id))
    transcript_id = summary.get("transcript_id")
    if not transcript_id:
        return summary, None

    transcript = await fetch_transcript_by_id(admin_client, str(transcript_id))
    return summary, transcript


async def _create_ready_reused_session(
    *,
    user_id: str,
    source: NormalizedSource,
    duration_seconds: int | None,
    summary_id: str,
    user_client: Any,
    admin_client: Any,
    settings: Settings,
) -> JobCreateResolution:
    job_resolution = await create_or_reuse_job(
        admin_client,
        url=source.canonical_url,
        source_key=source.source_identity_key,
        user_id=user_id,
        duration_seconds=duration_seconds,
        summary_id=summary_id,
    )
    if job_resolution.resolution_type != "new":
        job = await fetch_job(user_client, str(job_resolution.job["id"]))
        return JobCreateResolution(job=job, resolution_type=job_resolution.resolution_type)

    session_id = str(job_resolution.job["id"])
    lease_token = str(job_resolution.job.get("lease_token") or "")
    if not lease_token:
        raise UsageSettlementError("Cached briefing finalization did not receive a job lease.")
    try:
        await record_usage_for_job(
            user_id=user_id,
            job_id=session_id,
            lease_token=lease_token,
            duration_seconds=duration_seconds,
            settings=settings,
            admin_client=admin_client,
        )
        await mark_job_succeeded(
            admin_client,
            job_id=session_id,
            summary_id=summary_id,
            lease_token=lease_token,
        )
    except UsageSettlementError as exc:
        logger.warning(
            "briefing_session.usage_settlement.retrying",
            extra={"session_id": session_id},
            exc_info=True,
        )
        try:
            await mark_job_finalization_retry(
                admin_client,
                job_id=session_id,
                lease_token=lease_token,
                error_code=exc.code,
                error_message=exc.detail,
                run_after=_billing_retry_time(),
            )
        except JobLeaseLostError:
            logger.warning(
                "briefing_session.usage_settlement.retry_lease_lost",
                extra={"session_id": session_id},
            )
    except JobLeaseLostError:
        logger.warning(
            "briefing_session.finalization_lease_lost",
            extra={"session_id": session_id},
        )
    job = await fetch_job(user_client, session_id)
    return JobCreateResolution(job=job, resolution_type="new")


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

    transcript_id = str(transcript["id"])
    segments = await fetch_transcript_segments(
        admin_client,
        transcript_id=transcript_id,
    )
    prompt_key = SUMMARY_PROMPT_KEY_EVIDENCE if segments else SUMMARY_PROMPT_KEY_DEFAULT
    summary = await fetch_summary_by_keys(
        admin_client,
        transcript_id=transcript_id,
        prompt_key=prompt_key,
        summary_model=OPENROUTER_MODEL,
    )
    if not summary:
        return None

    markdown = summary.get("summary_markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        return None

    return summary


async def _job_has_ready_summary(user_client: Any, job: dict[str, Any]) -> bool:
    summary_id = job.get("summary_id")
    if not summary_id:
        return False

    summary = await fetch_summary(user_client, str(summary_id))
    markdown = summary.get("summary_markdown")
    return summary.get("status") == "ready" and isinstance(markdown, str) and bool(markdown.strip())


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _billing_retry_time() -> datetime:
    return datetime.now(UTC) + timedelta(seconds=5)


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


async def delete_briefing_session(session_id: UUID, auth: AuthContext, settings: Settings) -> None:
    session_id_str = str(session_id)
    with log_context(user_id=auth.user_id, session_id=session_id_str):
        user_client = await create_supabase_user_client(settings, auth.access_token)
        job = await fetch_job(user_client, session_id_str)
        if str(job.get("status") or "") == "deleted":
            return
        if not job.get("summary_id"):
            raise NotFoundError("Briefing session not found.")
        admin_client = await create_supabase_admin_client(settings)
        await archive_job(admin_client, job_id=session_id_str)


def _build_content_delta_event(
    snapshot: BriefingSessionResponse,
    delta: str,
    markdown_length: int,
) -> dict[str, Any]:
    return {
        "session_id": str(snapshot.session_id),
        "briefing_id": str(snapshot.briefing_id) if snapshot.briefing_id else None,
        "state": snapshot.state,
        "message": snapshot.message,
        "detail": snapshot.detail,
        "progress": snapshot.progress,
        "source_title": snapshot.source_title,
        "source_author": snapshot.source_author,
        "source_duration_seconds": snapshot.source_duration_seconds,
        "source_thumbnail_url": snapshot.source_thumbnail_url,
        "briefing_has_pdf": snapshot.briefing_has_pdf,
        "markdown_length": markdown_length,
        "delta": delta,
    }


def _build_status_event(snapshot: BriefingSessionResponse) -> dict[str, Any]:
    return {
        "session_id": str(snapshot.session_id),
        "briefing_id": str(snapshot.briefing_id) if snapshot.briefing_id else None,
        "state": snapshot.state,
        "message": snapshot.message,
        "detail": snapshot.detail,
        "progress": snapshot.progress,
        "resolution_type": snapshot.resolution_type,
        "source_title": snapshot.source_title,
        "source_author": snapshot.source_author,
        "source_duration_seconds": snapshot.source_duration_seconds,
        "source_thumbnail_url": snapshot.source_thumbnail_url,
        "briefing_has_pdf": snapshot.briefing_has_pdf,
        "error_code": snapshot.error_code,
        "error_message": snapshot.error_message,
    }

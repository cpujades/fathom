from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any
from uuid import UUID

from fathom.application.briefings.contract import encode_sse_event, normalize_source
from fathom.application.briefings.sessions.queries import build_session_snapshot
from fathom.application.identity import AuthenticatedUser
from fathom.core.config import Settings
from fathom.core.errors import NotFoundError, RateLimitError
from fathom.core.logging import log_context
from fathom.crud.supabase.job_events import fetch_latest_job_event_sequence, list_job_events_after
from fathom.crud.supabase.jobs import fetch_job
from fathom.crud.supabase.stream_leases import claim_stream_lease, release_stream_lease, renew_stream_lease
from fathom.schemas.briefing_sessions import BriefingSessionResponse
from fathom.services.supabase import (
    create_supabase_admin_client,
    create_supabase_user_client,
    managed_supabase_client,
)

logger = logging.getLogger(__name__)

KEEPALIVE_SECONDS = 15.0
EVENT_POLL_SECONDS = 1.0
SNAPSHOT_RECONCILE_SECONDS = 10.0
EVENT_BATCH_LIMIT = 100
MAX_REPLAY_EVENTS = 500


async def stream_briefing_session_events(
    session_id: UUID,
    auth: AuthenticatedUser,
    settings: Settings,
    *,
    client_subject: str,
    last_event_id: str | None,
    is_disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[str]:
    session_id_str = str(session_id)
    async with managed_supabase_client(await create_supabase_user_client(settings, auth.access_token)) as user_client:
        job = await fetch_job(user_client, session_id_str)
        if str(job.get("status") or "") == "deleted":
            raise NotFoundError("Briefing session not found.")

    async with managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client:
        stream_lease_token = await claim_stream_lease(
            admin_client,
            user_id=auth.user_id,
            client_subject=client_subject,
            max_per_user=settings.sse_max_streams_per_user,
            max_per_subject=settings.sse_max_streams_per_ip,
            lease_seconds=settings.sse_stream_lease_seconds,
        )
    if stream_lease_token is None:
        raise RateLimitError("Too many active briefing streams. Close another stream and try again.")

    return session_event_stream(
        session_id=session_id,
        auth=auth,
        settings=settings,
        last_event_id=last_event_id,
        is_disconnected=is_disconnected,
        stream_lease_token=stream_lease_token,
        initial_job=job,
    )


async def session_event_stream(
    *,
    session_id: UUID,
    auth: AuthenticatedUser,
    settings: Settings,
    last_event_id: str | None,
    is_disconnected: Callable[[], Awaitable[bool]],
    stream_lease_token: str | None = None,
    initial_job: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    async with (
        managed_supabase_client(await create_supabase_user_client(settings, auth.access_token)) as user_client,
        managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client,
    ):
        try:
            async for event in session_event_stream_with_clients(
                session_id=session_id,
                auth=auth,
                settings=settings,
                last_event_id=last_event_id,
                is_disconnected=is_disconnected,
                user_client=user_client,
                admin_client=admin_client,
                stream_lease_token=stream_lease_token,
                initial_job=initial_job,
            ):
                yield event
        finally:
            if stream_lease_token is not None:
                try:
                    await release_stream_lease(admin_client, lease_token=stream_lease_token)
                except Exception:
                    logger.warning(
                        "briefing_session.stream.release_failed",
                        extra={"session_id": str(session_id)},
                        exc_info=True,
                    )


async def session_event_stream_with_clients(
    *,
    session_id: UUID,
    auth: AuthenticatedUser,
    settings: Settings,
    last_event_id: str | None,
    is_disconnected: Callable[[], Awaitable[bool]],
    user_client: Any,
    admin_client: Any,
    stream_lease_token: str | None,
    initial_job: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    session_id_str = str(session_id)
    with log_context(user_id=auth.user_id, session_id=session_id_str):
        logger.info("briefing_session.stream.opened")

    job = initial_job if initial_job is not None else await fetch_job(user_client, session_id_str)
    if str(job.get("status") or "") == "deleted":
        raise NotFoundError("Briefing session not found.")

    latest_sequence = await fetch_latest_job_event_sequence(user_client, job_id=session_id_str)
    requested_cursor = parse_last_event_id(last_event_id)
    cursor = latest_sequence if requested_cursor is None else min(requested_cursor, latest_sequence)

    yield "retry: 2000\n\n"
    if requested_cursor is not None:
        replay_events, cursor = await replay_session_events(
            user_client=user_client,
            session_id=session_id_str,
            cursor=cursor,
            latest_sequence=latest_sequence,
        )
        for replay_event in replay_events:
            yield replay_event

    snapshot = await build_session_snapshot(
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
        log_stream_closed(auth.user_id, session_id_str, snapshot.state)
        return

    current_signature = snapshot_signature(snapshot)
    current_markdown = snapshot.briefing_markdown or ""
    seconds_since_snapshot = 0.0
    seconds_since_keepalive = 0.0
    stream_started_at = time.monotonic()
    lease_renewed_at = stream_started_at
    lease_renewal_interval = max(10.0, settings.sse_stream_lease_seconds / 3)

    while True:
        now = time.monotonic()
        if now - stream_started_at >= settings.sse_stream_max_lifetime_seconds:
            with log_context(user_id=auth.user_id, session_id=session_id_str):
                logger.info("briefing_session.stream.max_lifetime_reached")
            return

        if stream_lease_token is not None and now - lease_renewed_at >= lease_renewal_interval:
            renewed = await renew_stream_lease(
                admin_client,
                lease_token=stream_lease_token,
                lease_seconds=settings.sse_stream_lease_seconds,
            )
            if not renewed:
                with log_context(user_id=auth.user_id, session_id=session_id_str):
                    logger.warning("briefing_session.stream.lease_lost")
                return
            lease_renewed_at = now

        if await is_disconnected():
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
            sequence_id = event_sequence_id(event)
            if sequence_id is None:
                continue
            cursor = sequence_id
            yield encode_replayed_event(event, sequence_id)

        if events or seconds_since_snapshot >= SNAPSHOT_RECONCILE_SECONDS:
            latest_sequence = await fetch_latest_job_event_sequence(user_client, job_id=session_id_str)
            cursor = max(cursor, latest_sequence)
            refreshed_job = await fetch_job(user_client, session_id_str)
            refreshed_snapshot = await build_session_snapshot(
                user_client=user_client,
                admin_client=admin_client,
                job=refreshed_job,
                source=normalize_source(refreshed_job["url"]),
            )
            for encoded in encode_snapshot_changes(
                previous_signature=current_signature,
                previous_markdown=current_markdown,
                snapshot=refreshed_snapshot,
                cursor=cursor,
            ):
                yield encoded

            current_signature = snapshot_signature(refreshed_snapshot)
            current_markdown = refreshed_snapshot.briefing_markdown or ""
            seconds_since_snapshot = 0.0
            if refreshed_snapshot.state in {"ready", "failed"}:
                log_stream_closed(auth.user_id, session_id_str, refreshed_snapshot.state)
                return

        if seconds_since_keepalive >= KEEPALIVE_SECONDS:
            yield ": keepalive\n\n"
            seconds_since_keepalive = 0.0


async def replay_session_events(
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
            sequence_id = event_sequence_id(event)
            if sequence_id is None:
                continue
            cursor = sequence_id
            replayed += 1
            encoded_events.append(encode_replayed_event(event, sequence_id))
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


def encode_snapshot_changes(
    *,
    previous_signature: tuple[Any, ...],
    previous_markdown: str,
    snapshot: BriefingSessionResponse,
    cursor: int,
) -> Iterator[str]:
    markdown = snapshot.briefing_markdown or ""
    signature = snapshot_signature(snapshot)
    markdown_changed = markdown != previous_markdown

    if markdown_changed and markdown.startswith(previous_markdown):
        delta = markdown[len(previous_markdown) :]
        if delta:
            yield encode_sse_event(
                event_type="session.content_delta",
                event_id=str(cursor),
                data=build_content_delta_event(snapshot, delta, len(markdown)),
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
            data=build_status_event(snapshot),
        )

    if snapshot.state in {"ready", "failed"}:
        yield encode_sse_event(
            event_type="session.snapshot",
            event_id=str(cursor),
            data=snapshot.model_dump(mode="json"),
        )


def parse_last_event_id(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        cursor = int(value)
    except ValueError:
        return None
    return cursor if cursor >= 0 else None


def event_sequence_id(event: dict[str, Any]) -> int | None:
    value = event.get("sequence_id")
    return value if isinstance(value, int) and value > 0 else None


def encode_replayed_event(event: dict[str, Any], sequence_id: int) -> str:
    return encode_sse_event(
        event_type="session.event",
        event_id=str(sequence_id),
        data={
            "event_type": event.get("event_type"),
            "stage": event.get("stage"),
            "created_at": event.get("created_at"),
        },
    )


def log_stream_closed(user_id: str, session_id: str, state: str) -> None:
    with log_context(user_id=user_id, session_id=session_id):
        logger.info("briefing_session.stream.closed", extra={"state": state})


def snapshot_signature(snapshot: BriefingSessionResponse) -> tuple[Any, ...]:
    return (
        str(snapshot.session_id),
        str(snapshot.briefing_id) if snapshot.briefing_id else None,
        snapshot.state,
        snapshot.progress,
        snapshot.detail,
        snapshot.error_code,
        snapshot.error_message,
    )


def build_content_delta_event(
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


def build_status_event(snapshot: BriefingSessionResponse) -> dict[str, Any]:
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

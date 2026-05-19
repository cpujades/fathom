from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from typing import Any

from postgrest import APIError

from fathom.application.diagnostics.schemas import (
    JobTimeline,
    TimelineEvent,
    TimelineJob,
    TimelineSummary,
    TimelineTranscript,
)
from fathom.core.config import get_settings
from fathom.core.errors import NotFoundError
from fathom.crud.supabase.job_events import list_job_events
from fathom.services.supabase import create_supabase_admin_client
from fathom.services.supabase.helpers import first_row, raise_for_postgrest_error
from supabase import AsyncClient


async def fetch_job_timeline(client: AsyncClient, *, session_id: str) -> JobTimeline:
    job = await _fetch_job_snapshot(client, session_id=session_id)
    summary = await _fetch_summary_snapshot(client, summary_id=job.summary_id)
    transcript = await _fetch_transcript_snapshot(
        client,
        transcript_id=summary.transcript_id if summary else None,
    )
    events, events_unavailable = await _fetch_events_snapshot(client, session_id=session_id)

    return JobTimeline(
        session_id=session_id,
        job=job,
        summary=summary,
        transcript=transcript,
        events=events,
        events_unavailable=events_unavailable,
    )


def format_job_timeline(timeline: JobTimeline) -> str:
    lines = [
        "Talven job timeline",
        f"Session: {timeline.session_id}",
        f"Status: {timeline.job.status or 'unknown'}"
        f" / stage {timeline.job.stage or 'unknown'}"
        f" / progress {timeline.job.progress or 0}%",
        f"User: {timeline.job.user_id or 'unknown'}",
        f"URL: {timeline.job.url or 'unknown'}",
    ]

    if timeline.transcript:
        title = timeline.transcript.source_title or "Untitled source"
        author = timeline.transcript.source_author or "Unknown author"
        duration = _format_duration(timeline.transcript.source_length_seconds or timeline.job.duration_seconds)
        lines.append(f"Source: {title} by {author} ({duration})")
    elif timeline.job.duration_seconds is not None:
        lines.append(f"Source duration: {_format_duration(timeline.job.duration_seconds)}")

    if timeline.summary:
        lines.append(
            "Summary: "
            f"{timeline.summary.id} / "
            f"{timeline.summary.summary_model or 'unknown model'} / "
            f"{timeline.summary.markdown_chars} markdown chars"
        )

    if timeline.job.error_code:
        lines.append(f"Error: {timeline.job.error_code} - {timeline.job.error_message or 'No message'}")

    lines.append("")
    lines.append("Timeline:")
    if timeline.events:
        lines.extend(_format_event(event) for event in timeline.events)
    else:
        if timeline.events_unavailable:
            lines.append("- job_events unavailable; showing persisted row checkpoints.")
        else:
            lines.append("- no persisted job_events found; showing persisted row checkpoints.")
        lines.extend(_format_inferred_events(timeline))

    return "\n".join(lines)


async def _fetch_job_snapshot(client: AsyncClient, *, session_id: str) -> TimelineJob:
    try:
        response = (
            await client.table("jobs").select(TimelineJob.select_columns()).eq("id", session_id).limit(1).execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch job timeline.")

    try:
        row = first_row(response.data, error_message="Unexpected jobs shape.", not_found_message="Job not found.")
    except NotFoundError:
        raise NotFoundError(f"Job not found: {session_id}") from None
    return TimelineJob.model_validate(row)


async def _fetch_summary_snapshot(client: AsyncClient, *, summary_id: str | None) -> TimelineSummary | None:
    if not summary_id:
        return None

    try:
        response = (
            await client.table("summaries")
            .select(TimelineSummary.select_columns())
            .eq("id", summary_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch summary timeline.")

    data = response.data or []
    if not data:
        return None
    return TimelineSummary.model_validate(first_row(data, error_message="Unexpected summaries shape."))


async def _fetch_transcript_snapshot(client: AsyncClient, *, transcript_id: str | None) -> TimelineTranscript | None:
    if not transcript_id:
        return None

    try:
        response = (
            await client.table("transcripts")
            .select(TimelineTranscript.select_columns())
            .eq("id", transcript_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch transcript timeline.")

    data = response.data or []
    if not data:
        return None
    return TimelineTranscript.model_validate(first_row(data, error_message="Unexpected transcripts shape."))


async def _fetch_events_snapshot(client: AsyncClient, *, session_id: str) -> tuple[list[TimelineEvent], bool]:
    try:
        rows = await list_job_events(client, job_id=session_id)
    except Exception:
        return [], True
    return [TimelineEvent.model_validate(row) for row in rows], False


def _format_event(event: TimelineEvent) -> str:
    created_at = _format_datetime(event.created_at)
    label = event.event_type if not event.stage else f"{event.event_type} [{event.stage}]"
    detail = f" - {event.message}" if event.message else ""
    suffix = _format_metadata(event.metadata)
    return f"- {created_at}: {label}{detail}{suffix}"


def _format_inferred_events(timeline: JobTimeline) -> list[str]:
    job = timeline.job
    lines = [f"- {_format_datetime(job.created_at)}: session_created [queued]"]
    if job.claimed_at:
        lines.append(f"- {_format_datetime(job.claimed_at)}: job_claimed [running] (attempt={job.attempt_count})")
    if timeline.transcript:
        lines.append(
            f"- {_format_datetime(timeline.transcript.created_at)}: transcript_available"
            f" ({timeline.transcript.provider_model or 'unknown provider'})"
        )
    if timeline.summary:
        lines.append(
            f"- {_format_datetime(timeline.summary.created_at)}: summary_available"
            f" ({timeline.summary.summary_model or 'unknown model'}, "
            f"{timeline.summary.markdown_chars} markdown chars)"
        )
    if job.last_error_at:
        lines.append(f"- {_format_datetime(job.last_error_at)}: job_failed ({job.error_code or 'unknown_error'})")
    lines.append(f"- {_format_datetime(job.updated_at)}: latest_job_update [{job.stage}]")
    return lines


def _format_metadata(metadata: dict[str, Any]) -> str:
    keys = (
        "provider",
        "model",
        "summary_id",
        "transcript_id",
        "video_id",
        "duration_ms",
        "markdown_chars",
        "transcript_chars",
        "flush_count",
        "cache_hit",
        "error_code",
        "will_retry",
    )
    parts = [f"{key}={metadata[key]}" for key in keys if metadata.get(key) is not None]
    return f" ({', '.join(parts)})" if parts else ""


def _format_duration(value: Any) -> str:
    try:
        total_seconds = int(value)
    except (TypeError, ValueError):
        return "unknown duration"
    minutes, seconds = divmod(max(total_seconds, 0), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    return f"{minutes}m {seconds}s"


def _format_datetime(value: datetime | None) -> str:
    return value.isoformat() if value else "unknown time"


def main() -> None:
    parser = argparse.ArgumentParser(description="Show a local/admin timeline for a Talven briefing session.")
    parser.add_argument("session_id", help="Briefing session/job UUID.")
    parser.add_argument("--json", action="store_true", help="Print the raw timeline snapshot as JSON.")
    args = parser.parse_args()

    try:
        timeline = asyncio.run(_fetch_from_environment(args.session_id))
    except Exception as exc:
        print(f"Failed to fetch job timeline: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps(timeline.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    print(format_job_timeline(timeline))


async def _fetch_from_environment(session_id: str) -> JobTimeline:
    settings = get_settings()
    admin_client = await create_supabase_admin_client(settings)
    return await fetch_job_timeline(admin_client, session_id=session_id)


if __name__ == "__main__":
    main()

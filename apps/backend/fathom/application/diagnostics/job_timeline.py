from __future__ import annotations

from typing import Any

from postgrest import APIError

from fathom.core.errors import NotFoundError
from fathom.crud.supabase.job_events import list_job_events
from fathom.services.supabase.helpers import first_row, raise_for_postgrest_error
from supabase import AsyncClient

JOB_SELECT = (
    "id,user_id,status,url,summary_id,error_code,error_message,stage,progress,status_message,"
    "duration_seconds,attempt_count,created_at,updated_at,claimed_at,last_error_at,run_after"
)
SUMMARY_SELECT = (
    "id,user_id,transcript_id,prompt_key,summary_model,summary_markdown,pdf_object_key,created_at,ttl_expires_at"
)
TRANSCRIPT_SELECT = (
    "id,url_hash,video_id,provider_model,source_title,source_author,source_length_seconds,created_at,ttl_expires_at"
)


async def fetch_job_timeline(client: AsyncClient, *, session_id: str) -> dict[str, Any]:
    job = await _fetch_job_snapshot(client, session_id=session_id)
    summary = await _fetch_summary_snapshot(client, summary_id=_as_str(job.get("summary_id")))
    transcript = await _fetch_transcript_snapshot(
        client,
        transcript_id=_as_str(summary.get("transcript_id")) if summary else None,
    )
    events, events_unavailable = await _fetch_events_snapshot(client, session_id=session_id)

    return {
        "session_id": session_id,
        "job": job,
        "summary": summary,
        "transcript": transcript,
        "events": events,
        "events_unavailable": events_unavailable,
    }


def format_job_timeline(snapshot: dict[str, Any]) -> str:
    job = snapshot["job"]
    summary = snapshot.get("summary")
    transcript = snapshot.get("transcript")
    events = snapshot.get("events") or []
    events_unavailable = bool(snapshot.get("events_unavailable"))

    lines = [
        "Talven job timeline",
        f"Session: {snapshot['session_id']}",
        f"Status: {_as_str(job.get('status')) or 'unknown'}"
        f" / stage {_as_str(job.get('stage')) or 'unknown'}"
        f" / progress {_as_str(job.get('progress')) or '0'}%",
        f"User: {_as_str(job.get('user_id')) or 'unknown'}",
        f"URL: {_as_str(job.get('url')) or 'unknown'}",
    ]

    if transcript:
        title = _as_str(transcript.get("source_title")) or "Untitled source"
        author = _as_str(transcript.get("source_author")) or "Unknown author"
        duration = _format_duration(transcript.get("source_length_seconds") or job.get("duration_seconds"))
        lines.append(f"Source: {title} by {author} ({duration})")
    elif job.get("duration_seconds") is not None:
        lines.append(f"Source duration: {_format_duration(job.get('duration_seconds'))}")

    if summary:
        markdown = _as_str(summary.get("summary_markdown")) or ""
        lines.append(
            "Summary: "
            f"{_as_str(summary.get('id'))} / "
            f"{_as_str(summary.get('summary_model')) or 'unknown model'} / "
            f"{len(markdown)} markdown chars"
        )

    if job.get("error_code"):
        lines.append(f"Error: {job.get('error_code')} - {job.get('error_message') or 'No message'}")

    lines.append("")
    lines.append("Timeline:")

    if events:
        for event in events:
            lines.append(_format_event(event))
    else:
        if events_unavailable:
            lines.append("- job_events unavailable; showing persisted row checkpoints.")
        else:
            lines.append("- no persisted job_events found; showing persisted row checkpoints.")
        lines.extend(_format_inferred_events(job=job, summary=summary, transcript=transcript))

    return "\n".join(lines)


async def _fetch_job_snapshot(client: AsyncClient, *, session_id: str) -> dict[str, Any]:
    try:
        response = await client.table("jobs").select(JOB_SELECT).eq("id", session_id).limit(1).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch job timeline.")

    try:
        return first_row(response.data, error_message="Unexpected jobs shape.", not_found_message="Job not found.")
    except NotFoundError:
        raise NotFoundError(f"Job not found: {session_id}") from None


async def _fetch_summary_snapshot(client: AsyncClient, *, summary_id: str | None) -> dict[str, Any] | None:
    if not summary_id:
        return None

    try:
        response = await client.table("summaries").select(SUMMARY_SELECT).eq("id", summary_id).limit(1).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch summary timeline.")

    data = response.data or []
    if not data:
        return None
    return first_row(data, error_message="Unexpected summaries shape.")


async def _fetch_transcript_snapshot(client: AsyncClient, *, transcript_id: str | None) -> dict[str, Any] | None:
    if not transcript_id:
        return None

    try:
        response = (
            await client.table("transcripts").select(TRANSCRIPT_SELECT).eq("id", transcript_id).limit(1).execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch transcript timeline.")

    data = response.data or []
    if not data:
        return None
    return first_row(data, error_message="Unexpected transcripts shape.")


async def _fetch_events_snapshot(client: AsyncClient, *, session_id: str) -> tuple[list[dict[str, Any]], bool]:
    try:
        return await list_job_events(client, job_id=session_id), False
    except Exception:
        return [], True


def _format_event(event: dict[str, Any]) -> str:
    created_at = _as_str(event.get("created_at")) or "unknown time"
    event_type = _as_str(event.get("event_type")) or "event"
    stage = _as_str(event.get("stage"))
    message = _as_str(event.get("message"))
    raw_metadata = event.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    suffix = _format_metadata(metadata)

    label = event_type if not stage else f"{event_type} [{stage}]"
    detail = f" - {message}" if message else ""
    return f"- {created_at}: {label}{detail}{suffix}"


def _format_inferred_events(
    *,
    job: dict[str, Any],
    summary: dict[str, Any] | None,
    transcript: dict[str, Any] | None,
) -> list[str]:
    lines = [f"- {_as_str(job.get('created_at')) or 'unknown time'}: session_created [queued]"]
    if job.get("claimed_at"):
        lines.append(
            f"- {job['claimed_at']}: job_claimed [running] (attempt={_as_str(job.get('attempt_count')) or 'unknown'})"
        )
    if transcript:
        lines.append(
            f"- {_as_str(transcript.get('created_at')) or 'unknown time'}: transcript_available"
            f" ({_as_str(transcript.get('provider_model')) or 'unknown provider'})"
        )
    if summary:
        markdown = _as_str(summary.get("summary_markdown")) or ""
        lines.append(
            f"- {_as_str(summary.get('created_at')) or 'unknown time'}: summary_available"
            f" ({_as_str(summary.get('summary_model')) or 'unknown model'}, {len(markdown)} markdown chars)"
        )
    if job.get("last_error_at"):
        lines.append(f"- {job['last_error_at']}: job_failed ({_as_str(job.get('error_code')) or 'unknown_error'})")
    lines.append(f"- {_as_str(job.get('updated_at')) or 'unknown time'}: latest_job_update [{job.get('stage')}]")
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


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)

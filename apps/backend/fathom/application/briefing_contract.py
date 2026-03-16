from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from urllib.parse import ParseResult, parse_qsl, urlencode, urlparse, urlunparse

from fathom.schemas.briefing_sessions import (
    BriefingSessionResolution,
    BriefingSessionResponse,
    BriefingSessionState,
    BriefingSourceType,
)
from fathom.services.youtube import extract_youtube_video_id


@dataclass(frozen=True)
class NormalizedSource:
    submitted_url: str
    canonical_url: str
    source_type: BriefingSourceType
    source_identity_key: str
    video_id: str | None = None


def normalize_source(submitted_url: str) -> NormalizedSource:
    parsed = urlparse(submitted_url.strip())
    video_id = extract_youtube_video_id(parsed)
    if video_id:
        canonical_url = f"https://www.youtube.com/watch?v={video_id}"
        return NormalizedSource(
            submitted_url=submitted_url,
            canonical_url=canonical_url,
            source_type="youtube",
            source_identity_key=f"youtube:{video_id}",
            video_id=video_id,
        )

    canonical_url = _canonicalize_url(parsed)
    source_hash = sha256(canonical_url.encode("utf-8")).hexdigest()
    return NormalizedSource(
        submitted_url=submitted_url,
        canonical_url=canonical_url,
        source_type="url",
        source_identity_key=f"url:{source_hash}",
    )


def build_briefing_session_snapshot(
    *,
    job: dict[str, Any],
    source: NormalizedSource,
    resolution_type: BriefingSessionResolution | None = None,
    summary: dict[str, Any] | None = None,
    transcript: dict[str, Any] | None = None,
) -> BriefingSessionResponse:
    session_id = str(job["id"])
    state = _map_job_to_session_state(job)
    resolved_resolution = resolution_type or _infer_resolution_type(job)
    progress = _resolve_progress(job, state)
    message = _build_message(state, resolved_resolution)
    source_title = resolve_source_title(source, transcript.get("source_title") if transcript else None)
    source_author = _clean_optional_text(transcript.get("source_author") if transcript else None)
    source_duration_seconds = _resolve_source_duration_seconds(
        transcript.get("source_length_seconds") if transcript else None,
        job.get("duration_seconds"),
    )
    source_thumbnail_url = build_source_thumbnail_url(
        source,
        transcript.get("video_id") if transcript else None,
    )

    return BriefingSessionResponse(
        session_id=session_id,
        briefing_id=job.get("summary_id"),
        state=state,
        message=message,
        detail=job.get("status_message"),
        progress=progress,
        resolution_type=resolved_resolution,
        submitted_url=source.submitted_url,
        canonical_source_url=source.canonical_url,
        source_type=source.source_type,
        source_identity_key=source.source_identity_key,
        source_title=source_title,
        source_author=source_author,
        source_duration_seconds=source_duration_seconds,
        source_thumbnail_url=source_thumbnail_url,
        session_url=f"/briefing-sessions/{session_id}",
        events_url=f"/briefing-sessions/{session_id}/events",
        error_code=job.get("error_code"),
        error_message=job.get("error_message"),
        briefing_markdown=summary.get("summary_markdown") if summary else None,
        briefing_has_pdf=bool(summary and summary.get("pdf_object_key")),
    )


def encode_sse_event(*, event_type: str, event_id: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, separators=(",", ":"), default=str)
    lines = [f"id: {event_id}", f"event: {event_type}"]
    for line in payload.splitlines() or [""]:
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


def _canonicalize_url(parsed: ParseResult) -> str:
    normalized_query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=False)))
    normalized_path = parsed.path or "/"
    if normalized_path != "/":
        normalized_path = normalized_path.rstrip("/")

    return urlunparse(
        parsed._replace(
            scheme=(parsed.scheme or "https").lower(),
            netloc=(parsed.netloc or "").lower(),
            path=normalized_path,
            query=normalized_query,
            fragment="",
        )
    )


def _map_job_to_session_state(job: dict[str, Any]) -> BriefingSessionState:
    status = str(job.get("status") or "queued")
    stage = str(job.get("stage") or status)

    if status == "failed" or stage == "failed":
        return "failed"
    if status == "succeeded" or stage in {"completed", "cached"}:
        return "ready"
    if stage == "transcribing":
        return "transcribing"
    if stage == "checking_cache":
        return "reusing_existing"
    if stage == "summarizing":
        progress = job.get("progress")
        if isinstance(progress, int) and progress >= 90:
            return "finalizing_briefing"
        return "drafting_briefing"
    if stage == "finalizing":
        return "finalizing_briefing"
    if stage in {"queued"}:
        return "accepted"
    return "resolving_source"


def _infer_resolution_type(job: dict[str, Any]) -> BriefingSessionResolution:
    if str(job.get("stage") or "") == "cached":
        return "reused_ready"
    return "new"


def _resolve_progress(job: dict[str, Any], state: BriefingSessionState) -> int:
    progress = job.get("progress")
    if isinstance(progress, int):
        return max(0, min(progress, 100))

    defaults: dict[BriefingSessionState, int] = {
        "accepted": 8,
        "resolving_source": 18,
        "reusing_existing": 42,
        "transcribing": 34,
        "drafting_briefing": 68,
        "finalizing_briefing": 94,
        "ready": 100,
        "failed": 100,
    }
    return defaults[state]


def _build_message(state: BriefingSessionState, resolution_type: BriefingSessionResolution) -> str:
    if state == "ready" and resolution_type == "reused_ready":
        return "Using an existing briefing"
    if state == "ready":
        return "Your briefing is ready"
    if state == "failed":
        return "We couldn't finish this briefing"
    if state == "accepted":
        return "Briefing accepted"
    if state == "resolving_source":
        return "Resolving the source"
    if state == "reusing_existing":
        return "Checking reusable work"
    if state == "transcribing":
        return "Transcribing the audio"
    if state == "finalizing_briefing":
        return "Finalizing your briefing"
    return "Drafting your briefing"


def resolve_source_title(source: NormalizedSource, source_title: Any) -> str:
    cleaned = _clean_optional_text(source_title)
    if cleaned:
        return cleaned
    if source.source_type == "youtube":
        return "Untitled YouTube briefing"
    return "Untitled briefing"


def build_source_thumbnail_url(source: NormalizedSource, video_id: str | None = None) -> str | None:
    resolved_video_id = video_id or source.video_id
    if source.source_type != "youtube" or not isinstance(resolved_video_id, str) or not resolved_video_id:
        return None
    return f"https://i.ytimg.com/vi/{resolved_video_id}/hqdefault.jpg"


def _resolve_source_duration_seconds(primary: Any, fallback: Any) -> int | None:
    for candidate in (primary, fallback):
        if isinstance(candidate, int) and candidate > 0:
            return candidate
    return None


def _clean_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from dataclasses import dataclass

from fathom.application.briefing_renderer import render_briefing
from fathom.core.config import Settings
from fathom.core.constants import SUMMARY_PROMPT_KEY_EVIDENCE
from fathom.core.errors import ExternalServiceError
from fathom.crud.supabase.job_events import record_job_event_best_effort
from fathom.crud.supabase.jobs import update_job_progress
from fathom.crud.supabase.summaries import (
    fetch_summary_by_keys,
    mark_summary_failed,
    mark_summary_ready,
    prepare_summary,
    update_summary_markdown,
)
from fathom.orchestration.observability import log_stage, log_step
from fathom.schemas.transcripts import TranscriptSegment
from fathom.services.summarizer import (
    OPENROUTER_MODEL,
    summarize_transcript_with_evidence,
)
from supabase import AsyncClient

logger = logging.getLogger(__name__)

SUMMARY_CONTENTION_POLL_SECONDS = 2.0


@dataclass(frozen=True)
class SummaryResolution:
    summary_id: str
    markdown: str
    cache_hit: bool
    flush_count: int = 0


async def resolve_summary(
    *,
    job_id: str,
    user_id: str,
    requested_summary_id: str,
    transcript_id: str,
    settings: Settings,
    admin_client: AsyncClient,
    job_start: float,
    lease_token: str,
    transcript_segments: tuple[TranscriptSegment, ...] = (),
    source_video_id: str | None = None,
) -> SummaryResolution:
    if not transcript_segments:
        raise ExternalServiceError("Timestamped transcript evidence is unavailable; retrying transcription.")

    prompt_key = SUMMARY_PROMPT_KEY_EVIDENCE
    cached_summary = await _fetch_cached_summary(
        job_id=job_id,
        transcript_id=transcript_id,
        prompt_key=prompt_key,
        admin_client=admin_client,
        job_start=job_start,
        lease_token=lease_token,
    )
    if cached_summary:
        return await _use_cached_summary(
            job_id=job_id,
            summary_id=str(cached_summary["id"]),
            admin_client=admin_client,
            job_start=job_start,
            lease_token=lease_token,
        )

    preparation = await prepare_summary(
        admin_client,
        summary_id=requested_summary_id,
        user_id=user_id,
        job_id=job_id,
        generation_token=lease_token,
        transcript_id=transcript_id,
        prompt_key=prompt_key,
        summary_model=OPENROUTER_MODEL,
    )
    if preparation.resolution_type == "in_progress":
        await record_job_event_best_effort(
            admin_client,
            logger,
            job_id=job_id,
            event_type="summary_generation_waiting",
            stage="checking_cache",
            message="Waiting for the active summary producer.",
            metadata={
                "provider": "openrouter",
                "model": OPENROUTER_MODEL,
                "summary_id": str(preparation.summary["id"]),
            },
        )

    while preparation.resolution_type == "in_progress":
        await update_job_progress(
            admin_client,
            job_id=job_id,
            lease_token=lease_token,
            stage="checking_cache",
            progress=50,
            status_message="Waiting for an existing briefing",
        )
        await asyncio.sleep(SUMMARY_CONTENTION_POLL_SECONDS)
        preparation = await prepare_summary(
            admin_client,
            summary_id=requested_summary_id,
            user_id=user_id,
            job_id=job_id,
            generation_token=lease_token,
            transcript_id=transcript_id,
            prompt_key=prompt_key,
            summary_model=OPENROUTER_MODEL,
        )

    prepared_summary_id = str(preparation.summary["id"])
    if preparation.resolution_type == "ready":
        return await _use_cached_summary(
            job_id=job_id,
            summary_id=prepared_summary_id,
            admin_client=admin_client,
            job_start=job_start,
            lease_token=lease_token,
        )
    return await _create_evidence_summary(
        job_id=job_id,
        summary_id=prepared_summary_id,
        transcript_id=transcript_id,
        transcript_segments=transcript_segments,
        source_video_id=source_video_id,
        settings=settings,
        admin_client=admin_client,
        job_start=job_start,
        lease_token=lease_token,
    )


async def _fetch_cached_summary(
    *,
    job_id: str,
    transcript_id: str,
    prompt_key: str,
    admin_client: AsyncClient,
    job_start: float,
    lease_token: str,
) -> dict[str, object] | None:
    cache_check_start = time.perf_counter()
    log_stage(
        logger,
        "worker.summary.cache_check.started",
        job_start=job_start,
        stage="checking_cache",
        provider="openrouter",
        model=OPENROUTER_MODEL,
        prompt_key=prompt_key,
        transcript_id=transcript_id,
        level=logging.DEBUG,
    )
    await update_job_progress(
        admin_client,
        job_id=job_id,
        lease_token=lease_token,
        stage="checking_cache",
        progress=45,
        status_message="Checking for existing summaries",
    )
    cached_summary = await fetch_summary_by_keys(
        admin_client,
        transcript_id=transcript_id,
        prompt_key=prompt_key,
        summary_model=OPENROUTER_MODEL,
    )
    log_step(
        logger,
        "worker.summary.cache_check.completed",
        duration_ms=(time.perf_counter() - cache_check_start) * 1000,
        stage="checking_cache",
        provider="openrouter",
        model=OPENROUTER_MODEL,
        cache_hit=bool(cached_summary),
        level=logging.DEBUG,
    )
    return cached_summary


async def _use_cached_summary(
    *,
    job_id: str,
    summary_id: str,
    admin_client: AsyncClient,
    job_start: float,
    lease_token: str,
) -> SummaryResolution:
    log_stage(
        logger,
        "worker.summary.cache_hit",
        job_start=job_start,
        stage="cached",
        provider="openrouter",
        model=OPENROUTER_MODEL,
        summary_id=summary_id,
    )
    await record_job_event_best_effort(
        admin_client,
        logger,
        job_id=job_id,
        event_type="summary_cache_hit",
        stage="cached",
        message="Summary cache hit.",
        metadata={
            "provider": "openrouter",
            "model": OPENROUTER_MODEL,
            "summary_id": summary_id,
        },
    )
    await update_job_progress(
        admin_client,
        job_id=job_id,
        lease_token=lease_token,
        stage="finalizing",
        progress=96,
        status_message="Using an existing briefing",
        summary_id=summary_id,
    )
    return SummaryResolution(summary_id=summary_id, markdown="", cache_hit=True)


async def _create_evidence_summary(
    *,
    job_id: str,
    summary_id: str,
    transcript_id: str,
    transcript_segments: tuple[TranscriptSegment, ...],
    source_video_id: str | None,
    settings: Settings,
    admin_client: AsyncClient,
    job_start: float,
    lease_token: str,
) -> SummaryResolution:
    step_start = time.perf_counter()
    transcript_chars = sum(len(segment.text) for segment in transcript_segments)
    log_stage(
        logger,
        "worker.summary.started",
        job_start=job_start,
        stage="summarizing",
        provider="openrouter",
        model=OPENROUTER_MODEL,
        prompt_key=SUMMARY_PROMPT_KEY_EVIDENCE,
        summary_id=summary_id,
        transcript_id=transcript_id,
        transcript_chars=transcript_chars,
        transcript_segments=len(transcript_segments),
    )
    await record_job_event_best_effort(
        admin_client,
        logger,
        job_id=job_id,
        event_type="summary_started",
        stage="summarizing",
        message="Evidence-backed summary provider started.",
        metadata={
            "provider": "openrouter",
            "model": OPENROUTER_MODEL,
            "prompt_key": SUMMARY_PROMPT_KEY_EVIDENCE,
            "summary_id": summary_id,
            "transcript_id": transcript_id,
            "transcript_chars": transcript_chars,
            "transcript_segments": len(transcript_segments),
        },
    )
    await update_job_progress(
        admin_client,
        job_id=job_id,
        lease_token=lease_token,
        stage="summarizing",
        progress=60,
        status_message="Drafting your briefing",
        summary_id=summary_id,
    )

    try:
        contract = await summarize_transcript_with_evidence(
            transcript_segments,
            settings.openrouter_api_key,
        )
        markdown = render_briefing(
            contract,
            transcript_segments,
            source_video_id=source_video_id,
        )
        await update_summary_markdown(
            admin_client,
            summary_id=summary_id,
            generation_token=lease_token,
            summary_markdown=markdown,
        )
        await _record_first_markdown(
            job_id=job_id,
            summary_id=summary_id,
            markdown_chars=len(markdown),
            flush_count=1,
            admin_client=admin_client,
            job_start=job_start,
        )
        await mark_summary_ready(
            admin_client,
            summary_id=summary_id,
            generation_token=lease_token,
            summary_markdown=markdown,
        )
    except (Exception, asyncio.CancelledError):
        with suppress(Exception):
            await asyncio.shield(
                mark_summary_failed(
                    admin_client,
                    summary_id=summary_id,
                    generation_token=lease_token,
                )
            )
        raise

    await _record_summary_completed(
        job_id=job_id,
        summary_id=summary_id,
        markdown=markdown,
        flush_count=1,
        fallback_used=False,
        duration_ms=(time.perf_counter() - step_start) * 1000,
        admin_client=admin_client,
    )
    return SummaryResolution(
        summary_id=summary_id,
        markdown=markdown,
        cache_hit=False,
        flush_count=1,
    )


async def _record_first_markdown(
    *,
    job_id: str,
    summary_id: str,
    markdown_chars: int,
    flush_count: int,
    admin_client: AsyncClient,
    job_start: float,
) -> None:
    log_stage(
        logger,
        "worker.summary.first_markdown_persisted",
        job_start=job_start,
        stage="summarizing",
        provider="openrouter",
        model=OPENROUTER_MODEL,
        chars=markdown_chars,
        flush_count=flush_count,
    )
    await record_job_event_best_effort(
        admin_client,
        logger,
        job_id=job_id,
        event_type="first_markdown_persisted",
        stage="summarizing",
        message="First briefing text persisted.",
        metadata={
            "summary_id": summary_id,
            "markdown_chars": markdown_chars,
            "flush_count": flush_count,
        },
    )


async def _record_summary_completed(
    *,
    job_id: str,
    summary_id: str,
    markdown: str,
    flush_count: int,
    fallback_used: bool,
    duration_ms: float,
    admin_client: AsyncClient,
) -> None:
    log_step(
        logger,
        "worker.summary.completed",
        duration_ms=duration_ms,
        stage="summarizing",
        provider="openrouter",
        model=OPENROUTER_MODEL,
        markdown_chars=len(markdown),
        flush_count=flush_count,
        fallback_used=fallback_used,
    )
    await record_job_event_best_effort(
        admin_client,
        logger,
        job_id=job_id,
        event_type="summary_completed",
        stage="summarizing",
        message="Summary completed.",
        metadata={
            "provider": "openrouter",
            "model": OPENROUTER_MODEL,
            "summary_id": summary_id,
            "markdown_chars": len(markdown),
            "flush_count": flush_count,
            "fallback_used": fallback_used,
            "duration_ms": round(duration_ms, 2),
        },
    )

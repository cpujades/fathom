from __future__ import annotations

import logging
import time
import uuid
from urllib.parse import urlparse

from fathom.application.usage import record_usage_for_job
from fathom.core.config import Settings
from fathom.core.constants import GROQ_MODEL, SUMMARY_PROMPT_KEY_DEFAULT
from fathom.core.logging import log_context
from fathom.crud.supabase.job_events import record_job_event_best_effort
from fathom.crud.supabase.jobs import mark_job_succeeded, update_job_progress
from fathom.orchestration.observability import log_stage, log_step
from fathom.orchestration.summaries import resolve_summary
from fathom.orchestration.transcripts import resolve_transcript
from fathom.services.summarizer import OPENROUTER_MODEL
from supabase import AsyncClient

logger = logging.getLogger(__name__)


async def process_job(job: dict[str, object], settings: Settings, admin_client: AsyncClient) -> None:
    job_id = str(job["id"])
    url = str(job["url"])
    user_id = str(job["user_id"])
    requested_summary_id = str(uuid.uuid4())
    job_start = time.perf_counter()

    with log_context(job_id=job_id, user_id=user_id, summary_id=requested_summary_id):
        logger.info(
            "worker.job.started",
            extra={
                "url_host": urlparse(url).netloc.lower(),
                "transcript_provider": "groq",
                "transcript_model": GROQ_MODEL,
                "summary_provider": "openrouter",
                "summary_model": OPENROUTER_MODEL,
                "prompt_key": SUMMARY_PROMPT_KEY_DEFAULT,
            },
        )
        await update_job_progress(
            admin_client,
            job_id=job_id,
            stage="warming",
            progress=10,
            status_message="Warming up the studio",
        )
        await update_job_progress(
            admin_client,
            job_id=job_id,
            stage="transcribing",
            progress=30,
            status_message="Transcribing the audio",
        )

        transcript = await resolve_transcript(
            job_id=job_id,
            url=url,
            settings=settings,
            admin_client=admin_client,
            job_start=job_start,
        )
        summary = await resolve_summary(
            job_id=job_id,
            user_id=user_id,
            requested_summary_id=requested_summary_id,
            transcript_id=transcript.transcript_id,
            transcript_text=transcript.transcript_text,
            settings=settings,
            admin_client=admin_client,
            job_start=job_start,
        )

        if not summary.cache_hit:
            await _finalize_new_summary(
                job_id=job_id,
                summary_id=summary.summary_id,
                markdown=summary.markdown,
                admin_client=admin_client,
                job_start=job_start,
            )

        await _record_usage(job=job, user_id=user_id, job_id=job_id, settings=settings)
        await _record_job_completed(
            job_id=job_id,
            summary_id=summary.summary_id,
            cache_hit=summary.cache_hit,
            markdown=summary.markdown,
            flush_count=summary.flush_count,
            admin_client=admin_client,
            job_start=job_start,
        )


async def _finalize_new_summary(
    *,
    job_id: str,
    summary_id: str,
    markdown: str,
    admin_client: AsyncClient,
    job_start: float,
) -> None:
    log_stage(
        logger,
        "worker.stage.started",
        job_start=job_start,
        stage="finalizing",
        summary_id=summary_id,
        markdown_chars=len(markdown),
        level=logging.DEBUG,
    )
    await update_job_progress(
        admin_client,
        job_id=job_id,
        stage="finalizing",
        progress=96,
        status_message="Finalizing your briefing",
        summary_id=summary_id,
    )
    await update_job_progress(
        admin_client,
        job_id=job_id,
        stage="completed",
        progress=100,
        status_message="Summary ready",
        summary_id=summary_id,
    )
    with log_context(summary_id=summary_id):
        await mark_job_succeeded(admin_client, job_id=job_id, summary_id=summary_id)


async def _record_usage(*, job: dict[str, object], user_id: str, job_id: str, settings: Settings) -> None:
    try:
        await record_usage_for_job(
            user_id=user_id,
            job_id=job_id,
            duration_seconds=_duration_seconds(job.get("duration_seconds")),
            settings=settings,
        )
    except Exception:
        logger.exception("worker.usage_recording.failed", extra={"job_id": job_id})


def _duration_seconds(value: object) -> int | None:
    return value if isinstance(value, int) else None


async def _record_job_completed(
    *,
    job_id: str,
    summary_id: str,
    cache_hit: bool,
    markdown: str,
    flush_count: int,
    admin_client: AsyncClient,
    job_start: float,
) -> None:
    duration_ms = (time.perf_counter() - job_start) * 1000
    log_step(
        logger,
        "worker.job.completed",
        duration_ms=duration_ms,
        cache_hit=cache_hit,
        stage="completed",
        provider="openrouter",
        model=OPENROUTER_MODEL,
        summary_id=summary_id,
        markdown_chars=len(markdown) if markdown else None,
        flush_count=flush_count,
    )
    await record_job_event_best_effort(
        admin_client,
        logger,
        job_id=job_id,
        event_type="job_completed",
        stage="completed",
        message="Cached briefing ready." if cache_hit else "Briefing ready.",
        metadata={
            "cache_hit": cache_hit,
            "duration_ms": round(duration_ms, 2),
            "summary_id": summary_id,
            "markdown_chars": len(markdown) if markdown else None,
            "flush_count": flush_count,
        },
    )

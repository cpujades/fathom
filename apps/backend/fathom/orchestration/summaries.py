from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from fathom.core.config import Settings
from fathom.core.constants import SUMMARY_PROMPT_KEY_DEFAULT
from fathom.crud.supabase.job_events import record_job_event_best_effort
from fathom.crud.supabase.jobs import mark_job_succeeded, update_job_progress
from fathom.crud.supabase.summaries import create_summary, fetch_summary_by_keys, update_summary_markdown
from fathom.orchestration.observability import elapsed_ms, log_stage, log_step
from fathom.services.summarizer import OPENROUTER_MODEL, stream_summarize_transcript, summarize_transcript
from supabase import AsyncClient

logger = logging.getLogger(__name__)

STREAM_FLUSH_CHAR_THRESHOLD = 80
STREAM_FLUSH_SECONDS = 0.35


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
    transcript_text: str,
    settings: Settings,
    admin_client: AsyncClient,
    job_start: float,
) -> SummaryResolution:
    cached_summary = await _fetch_cached_summary(
        job_id=job_id,
        transcript_id=transcript_id,
        admin_client=admin_client,
        job_start=job_start,
    )
    if cached_summary:
        return await _use_cached_summary(
            job_id=job_id,
            summary_id=str(cached_summary["id"]),
            admin_client=admin_client,
            job_start=job_start,
        )

    return await _create_streaming_summary(
        job_id=job_id,
        user_id=user_id,
        requested_summary_id=requested_summary_id,
        transcript_id=transcript_id,
        transcript_text=transcript_text,
        settings=settings,
        admin_client=admin_client,
        job_start=job_start,
    )


async def _fetch_cached_summary(
    *,
    job_id: str,
    transcript_id: str,
    admin_client: AsyncClient,
    job_start: float,
) -> dict[str, object] | None:
    cache_check_start = time.perf_counter()
    log_stage(
        logger,
        "worker.summary.cache_check.started",
        job_start=job_start,
        stage="checking_cache",
        provider="openrouter",
        model=OPENROUTER_MODEL,
        prompt_key=SUMMARY_PROMPT_KEY_DEFAULT,
        transcript_id=transcript_id,
        level=logging.DEBUG,
    )
    await update_job_progress(
        admin_client,
        job_id=job_id,
        stage="checking_cache",
        progress=45,
        status_message="Checking for existing summaries",
    )
    cached_summary = await fetch_summary_by_keys(
        admin_client,
        transcript_id=transcript_id,
        prompt_key=SUMMARY_PROMPT_KEY_DEFAULT,
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
        stage="cached",
        progress=100,
        status_message="Summary ready (cached)",
        summary_id=summary_id,
    )
    await mark_job_succeeded(admin_client, job_id=job_id, summary_id=summary_id)
    return SummaryResolution(summary_id=summary_id, markdown="", cache_hit=True)


async def _create_streaming_summary(
    *,
    job_id: str,
    user_id: str,
    requested_summary_id: str,
    transcript_id: str,
    transcript_text: str,
    settings: Settings,
    admin_client: AsyncClient,
    job_start: float,
) -> SummaryResolution:
    step_start = time.perf_counter()
    summary_row = await create_summary(
        admin_client,
        summary_id=requested_summary_id,
        user_id=user_id,
        transcript_id=transcript_id,
        prompt_key=SUMMARY_PROMPT_KEY_DEFAULT,
        summary_model=OPENROUTER_MODEL,
        summary_markdown="",
        pdf_object_key=None,
    )
    summary_id = str(summary_row["id"])
    log_stage(
        logger,
        "worker.summary.started",
        job_start=job_start,
        stage="summarizing",
        provider="openrouter",
        model=OPENROUTER_MODEL,
        prompt_key=SUMMARY_PROMPT_KEY_DEFAULT,
        summary_id=summary_id,
        transcript_id=transcript_id,
        transcript_chars=len(transcript_text),
    )
    await record_job_event_best_effort(
        admin_client,
        logger,
        job_id=job_id,
        event_type="summary_started",
        stage="summarizing",
        message="Summary provider started.",
        metadata={
            "provider": "openrouter",
            "model": OPENROUTER_MODEL,
            "summary_id": summary_id,
            "transcript_id": transcript_id,
            "transcript_chars": len(transcript_text),
        },
    )
    await update_job_progress(
        admin_client,
        job_id=job_id,
        stage="summarizing",
        progress=60,
        status_message="Drafting your briefing",
        summary_id=summary_id,
    )

    markdown, flush_count, fallback_used = await _stream_summary_markdown(
        job_id=job_id,
        summary_id=summary_id,
        transcript_text=transcript_text,
        settings=settings,
        admin_client=admin_client,
        job_start=job_start,
    )
    await _record_summary_completed(
        job_id=job_id,
        summary_id=summary_id,
        markdown=markdown,
        flush_count=flush_count,
        fallback_used=fallback_used,
        duration_ms=(time.perf_counter() - step_start) * 1000,
        admin_client=admin_client,
    )
    return SummaryResolution(
        summary_id=summary_id,
        markdown=markdown,
        cache_hit=False,
        flush_count=flush_count,
    )


async def _stream_summary_markdown(
    *,
    job_id: str,
    summary_id: str,
    transcript_text: str,
    settings: Settings,
    admin_client: AsyncClient,
    job_start: float,
) -> tuple[str, int, bool]:
    summary_markdown = ""
    last_flush_len = 0
    last_flush_time = time.monotonic()
    progress = 60
    flush_count = 0
    first_visible_logged = False
    first_stream_chunk_logged = False
    message_index = 0
    status_messages = [
        "Pulling out the best insights",
        "Connecting the dots",
        "Highlighting the sharpest moments",
        "Building your action list",
        "Polishing the key takeaways",
        "Shaping the final narrative",
    ]

    stream_failed = False
    try:
        async for delta in stream_summarize_transcript(transcript_text, settings.openrouter_api_key):
            summary_markdown += delta
            if not first_stream_chunk_logged:
                log_stage(
                    logger,
                    "worker.summary.first_stream_chunk",
                    job_start=job_start,
                    stage="summarizing",
                    provider="openrouter",
                    model=OPENROUTER_MODEL,
                    chunk_chars=len(delta),
                    level=logging.DEBUG,
                )
                first_stream_chunk_logged = True

            if not _should_flush(summary_markdown, last_flush_len, last_flush_time):
                continue

            await update_summary_markdown(
                admin_client,
                summary_id=summary_id,
                summary_markdown=summary_markdown,
            )
            flush_count += 1
            last_flush_len = len(summary_markdown)
            last_flush_time = time.monotonic()
            if not first_visible_logged:
                await _record_first_markdown(
                    job_id=job_id,
                    summary_id=summary_id,
                    markdown_chars=len(summary_markdown),
                    flush_count=flush_count,
                    admin_client=admin_client,
                    job_start=job_start,
                )
                first_visible_logged = True
            progress = min(progress + 1, 92)
            await update_job_progress(
                admin_client,
                job_id=job_id,
                stage="summarizing",
                progress=progress,
                status_message=status_messages[message_index % len(status_messages)],
            )
            message_index += 1
    except Exception:
        stream_failed = True
        logger.warning(
            "worker.summary.stream_failed",
            extra={
                "elapsed_ms": elapsed_ms(job_start),
                "stage": "summarizing",
                "provider": "openrouter",
                "model": OPENROUTER_MODEL,
                "streamed_chars": len(summary_markdown),
                "flush_count": flush_count,
                "error_code": "summary_stream_failed",
            },
            exc_info=True,
        )

    if stream_failed or not summary_markdown.strip():
        summary_markdown = await _fallback_summary(
            job_id=job_id,
            transcript_text=transcript_text,
            settings=settings,
            admin_client=admin_client,
            progress=progress,
            stream_failed=stream_failed,
            streamed_chars=len(summary_markdown),
            flush_count=flush_count,
        )

    if summary_markdown:
        await update_summary_markdown(
            admin_client,
            summary_id=summary_id,
            summary_markdown=summary_markdown,
        )
        if not first_visible_logged:
            await _record_first_markdown(
                job_id=job_id,
                summary_id=summary_id,
                markdown_chars=len(summary_markdown),
                flush_count=flush_count,
                admin_client=admin_client,
                job_start=job_start,
            )

    return summary_markdown, flush_count, stream_failed


async def _fallback_summary(
    *,
    job_id: str,
    transcript_text: str,
    settings: Settings,
    admin_client: AsyncClient,
    progress: int,
    stream_failed: bool,
    streamed_chars: int,
    flush_count: int,
) -> str:
    fallback_start = time.perf_counter()
    logger.warning(
        "worker.summary.fallback.started",
        extra={
            "stage": "summarizing",
            "provider": "openrouter",
            "model": OPENROUTER_MODEL,
            "stream_failed": stream_failed,
            "streamed_chars": streamed_chars,
            "flush_count": flush_count,
        },
    )
    await record_job_event_best_effort(
        admin_client,
        logger,
        job_id=job_id,
        event_type="summary_fallback_started",
        stage="summarizing",
        message="Streaming summary fell back to full summary.",
        metadata={
            "provider": "openrouter",
            "model": OPENROUTER_MODEL,
            "stream_failed": stream_failed,
            "streamed_chars": streamed_chars,
            "flush_count": flush_count,
        },
    )
    await update_job_progress(
        admin_client,
        job_id=job_id,
        stage="summarizing",
        progress=min(progress + 5, 92),
        status_message="Finalizing a full summary",
    )
    markdown = await summarize_transcript(transcript_text, settings.openrouter_api_key)
    log_step(
        logger,
        "worker.summary.fallback.completed",
        duration_ms=(time.perf_counter() - fallback_start) * 1000,
        stage="summarizing",
        provider="openrouter",
        model=OPENROUTER_MODEL,
        markdown_chars=len(markdown),
    )
    return markdown


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


def _should_flush(markdown: str, last_flush_len: int, last_flush_time: float) -> bool:
    if len(markdown) - last_flush_len >= STREAM_FLUSH_CHAR_THRESHOLD:
        return True
    return time.monotonic() - last_flush_time >= STREAM_FLUSH_SECONDS

from __future__ import annotations

import asyncio
import hashlib
import logging
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from fathom.application.billing import run_billing_maintenance
from fathom.application.usage import record_usage_for_job
from fathom.core.config import Settings, get_settings
from fathom.core.constants import (
    GROQ_MODEL,
    GROQ_SIGNED_URL_TTL_SECONDS,
    SUMMARY_PROMPT_KEY_DEFAULT,
    SUPABASE_GROQ_BUCKET,
)
from fathom.core.logging import log_context, setup_logging
from fathom.crud.supabase.jobs import (
    claim_next_job,
    mark_job_failed,
    mark_job_retry,
    mark_job_succeeded,
    requeue_stale_jobs,
    update_job_progress,
)
from fathom.crud.supabase.storage_objects import create_signed_url, delete_object, upload_object
from fathom.crud.supabase.summaries import create_summary, fetch_summary_by_keys, update_summary_markdown
from fathom.crud.supabase.transcripts import (
    create_transcript,
    fetch_transcript_by_hash,
    fetch_transcript_by_video_id,
)
from fathom.orchestration.observability import (
    elapsed_ms,
    extract_job_error,
    log_stage,
    log_step,
    record_timeline_event,
)
from fathom.services.downloader import download_audio
from fathom.services.summarizer import (
    OPENROUTER_MODEL,
    stream_summarize_transcript,
    summarize_transcript,
)
from fathom.services.supabase import create_supabase_admin_client, listen_for_notifications
from fathom.services.transcriber import transcribe_url
from fathom.services.youtube import extract_youtube_video_id
from supabase import AsyncClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Worker configuration
# ---------------------------------------------------------------------------
WORKER_IDLE_SLEEP_SECONDS = 1
WORKER_MAX_ATTEMPTS = 3
WORKER_BACKOFF_BASE_SECONDS = 5
WORKER_STALE_AFTER_SECONDS = 300  # 5 minutes
WORKER_SWEEP_INTERVAL_SECONDS = 30.0
WORKER_BILLING_MAINTENANCE_INTERVAL_SECONDS = 60.0
WORKER_JOB_NOTIFY_TIMEOUT_SECONDS = 10.0

# Streaming summary flush tuning
STREAM_FLUSH_CHAR_THRESHOLD = 80
STREAM_FLUSH_SECONDS = 0.35


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _compute_backoff_seconds(base: int, attempt: int) -> int:
    return int(base * (2 ** max(attempt - 1, 0)))


def _log_step(label: str, *, duration_ms: float, level: int = logging.INFO, **fields: object) -> None:
    log_step(logger, label, duration_ms=duration_ms, level=level, **fields)


def _log_stage(
    label: str,
    *,
    job_start: float,
    stage: str,
    level: int = logging.INFO,
    **fields: object,
) -> None:
    log_stage(logger, label, job_start=job_start, stage=stage, level=level, **fields)


async def _resolve_transcript(
    *,
    job_id: str,
    url: str,
    settings: Settings,
    admin_client: AsyncClient,
    job_start: float,
) -> tuple[str, str, str | None]:
    """Return (transcript_id, transcript_text, video_id_or_hash)."""
    url_hash = _hash_url(url)
    parsed_url = urlparse(url)
    parsed_video_id = extract_youtube_video_id(parsed_url)
    transcript_text: str
    video_id: str | None = None
    provider_model = f"groq:{GROQ_MODEL}"

    transcript_row = None
    if parsed_video_id:
        transcript_row = await fetch_transcript_by_video_id(
            admin_client,
            video_id=parsed_video_id,
            provider_model=provider_model,
        )

    if not transcript_row:
        transcript_row = await fetch_transcript_by_hash(
            admin_client,
            url_hash=url_hash,
            provider_model=provider_model,
        )

    if transcript_row:
        transcript_text = transcript_row["transcript_text"]
        video_id = transcript_row.get("video_id") or parsed_video_id
        transcript_id = transcript_row["id"]
        _log_stage(
            "worker.transcript.cache_hit",
            job_start=job_start,
            stage="transcribing",
            provider="groq",
            model=GROQ_MODEL,
            transcript_id=transcript_id,
            video_id=video_id,
            transcript_chars=len(transcript_text),
        )
        await record_timeline_event(
            admin_client,
            logger,
            job_id=job_id,
            event_type="transcript_cache_hit",
            stage="transcribing",
            message="Transcript cache hit.",
            metadata={
                "provider": "groq",
                "model": GROQ_MODEL,
                "transcript_id": transcript_id,
                "video_id": video_id,
                "transcript_chars": len(transcript_text),
            },
        )
        return transcript_id, transcript_text, video_id or url_hash

    with tempfile.TemporaryDirectory() as tmp_dir:
        _log_stage(
            "worker.audio.download.started",
            job_start=job_start,
            stage="transcribing",
            video_id=parsed_video_id,
            level=logging.DEBUG,
        )
        step_start = time.perf_counter()
        download_result = await asyncio.to_thread(download_audio, url, tmp_dir)
        _log_step(
            "worker.audio.downloaded",
            duration_ms=(time.perf_counter() - step_start) * 1000,
            stage="transcribing",
            video_id=parsed_video_id,
            bytes=download_result.filesize_bytes,
        )
        video_id = download_result.video_id or parsed_video_id
        await record_timeline_event(
            admin_client,
            logger,
            job_id=job_id,
            event_type="source_downloaded",
            stage="transcribing",
            message="Source audio downloaded.",
            metadata={
                "video_id": video_id,
                "bytes": download_result.filesize_bytes,
                "duration_ms": round((time.perf_counter() - step_start) * 1000, 2),
            },
        )

        object_key = f"groq-audio/{uuid.uuid4().hex}.{download_result.subtype or 'bin'}"
        audio_bytes = await asyncio.to_thread(download_result.path.read_bytes)
        content_type = download_result.mime_type or "application/octet-stream"
        await upload_object(
            admin_client,
            bucket=SUPABASE_GROQ_BUCKET,
            object_key=object_key,
            data=audio_bytes,
            content_type=content_type,
        )
        try:
            signed_url = await create_signed_url(
                admin_client,
                bucket=SUPABASE_GROQ_BUCKET,
                object_key=object_key,
                ttl_seconds=GROQ_SIGNED_URL_TTL_SECONDS,
            )
            _log_stage(
                "worker.transcription.provider.started",
                job_start=job_start,
                stage="transcribing",
                provider="groq",
                model=GROQ_MODEL,
                audio_bytes=download_result.filesize_bytes,
                level=logging.DEBUG,
            )
            await record_timeline_event(
                admin_client,
                logger,
                job_id=job_id,
                event_type="transcription_started",
                stage="transcribing",
                message="Transcription provider started.",
                metadata={"provider": "groq", "model": GROQ_MODEL, "audio_bytes": download_result.filesize_bytes},
            )
            step_start = time.perf_counter()
            transcript_text = await asyncio.to_thread(
                transcribe_url,
                signed_url,
                settings.groq_api_key,
                GROQ_MODEL,
            )
            _log_step(
                "worker.transcript.created",
                duration_ms=(time.perf_counter() - step_start) * 1000,
                stage="transcribing",
                provider="groq",
                model=GROQ_MODEL,
                transcript_chars=len(transcript_text),
            )
            await record_timeline_event(
                admin_client,
                logger,
                job_id=job_id,
                event_type="transcription_completed",
                stage="transcribing",
                message="Transcript created.",
                metadata={
                    "provider": "groq",
                    "model": GROQ_MODEL,
                    "transcript_chars": len(transcript_text),
                    "duration_ms": round((time.perf_counter() - step_start) * 1000, 2),
                },
            )
        finally:
            try:
                await delete_object(
                    admin_client,
                    bucket=SUPABASE_GROQ_BUCKET,
                    object_key=object_key,
                )
            except Exception:
                logger.warning("worker.audio.cleanup_failed", exc_info=True)

    transcript_row = await create_transcript(
        admin_client,
        url_hash=url_hash,
        video_id=video_id,
        transcript_text=transcript_text,
        provider_model=provider_model,
        source_title=download_result.title,
        source_author=download_result.author,
        source_description=download_result.description,
        source_keywords=download_result.keywords,
        source_views=download_result.views,
        source_likes=download_result.likes,
        source_length_seconds=download_result.length_seconds,
    )
    transcript_id = transcript_row["id"]
    _log_stage(
        "worker.transcript.persisted",
        job_start=job_start,
        stage="transcribing",
        provider="groq",
        model=GROQ_MODEL,
        transcript_id=transcript_id,
        video_id=video_id,
        transcript_chars=len(transcript_text),
        level=logging.DEBUG,
    )
    await record_timeline_event(
        admin_client,
        logger,
        job_id=job_id,
        event_type="transcript_persisted",
        stage="transcribing",
        message="Transcript persisted.",
        metadata={
            "provider": "groq",
            "model": GROQ_MODEL,
            "transcript_id": transcript_id,
            "video_id": video_id,
            "transcript_chars": len(transcript_text),
        },
    )
    return transcript_id, transcript_text, video_id or url_hash


async def _process_job(job: dict[str, Any], settings: Settings, admin_client: AsyncClient) -> None:
    job_id = job["id"]
    url = job["url"]
    user_id = job["user_id"]
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
        transcript_id, transcript_text, _video_segment = await _resolve_transcript(
            job_id=job_id,
            url=url,
            settings=settings,
            admin_client=admin_client,
            job_start=job_start,
        )

        cache_check_start = time.perf_counter()
        _log_stage(
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
        _log_step(
            "worker.summary.cache_check.completed",
            duration_ms=(time.perf_counter() - cache_check_start) * 1000,
            stage="checking_cache",
            provider="openrouter",
            model=OPENROUTER_MODEL,
            cache_hit=bool(cached_summary),
            level=logging.DEBUG,
        )
        if cached_summary:
            cached_summary_id = cached_summary["id"]
            _log_stage(
                "worker.summary.cache_hit",
                job_start=job_start,
                stage="cached",
                provider="openrouter",
                model=OPENROUTER_MODEL,
                summary_id=cached_summary_id,
            )
            await record_timeline_event(
                admin_client,
                logger,
                job_id=job_id,
                event_type="summary_cache_hit",
                stage="cached",
                message="Summary cache hit.",
                metadata={
                    "provider": "openrouter",
                    "model": OPENROUTER_MODEL,
                    "summary_id": cached_summary_id,
                },
            )
            with log_context(summary_id=cached_summary_id):
                await update_job_progress(
                    admin_client,
                    job_id=job_id,
                    stage="cached",
                    progress=100,
                    status_message="Summary ready (cached)",
                    summary_id=cached_summary_id,
                )
                await mark_job_succeeded(admin_client, job_id=job_id, summary_id=cached_summary_id)
                try:
                    await record_usage_for_job(
                        user_id=user_id,
                        job_id=job_id,
                        duration_seconds=job.get("duration_seconds"),
                        settings=settings,
                    )
                except Exception:
                    logger.exception("worker.usage_recording.failed", extra={"job_id": job_id, "cache_hit": True})
            _log_step(
                "worker.job.completed",
                duration_ms=(time.perf_counter() - job_start) * 1000,
                cache_hit=True,
                stage="completed",
                provider="openrouter",
                model=OPENROUTER_MODEL,
                summary_id=cached_summary_id,
            )
            await record_timeline_event(
                admin_client,
                logger,
                job_id=job_id,
                event_type="job_completed",
                stage="completed",
                message="Cached briefing ready.",
                metadata={
                    "cache_hit": True,
                    "duration_ms": round((time.perf_counter() - job_start) * 1000, 2),
                    "summary_id": cached_summary_id,
                },
            )
            return

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
        summary_id = summary_row["id"]
        _log_stage(
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
        await record_timeline_event(
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

        summary_markdown = ""
        last_flush_len = 0
        last_flush_time = time.monotonic()
        progress = 60
        flush_count = 0
        first_visible_logged = False
        first_stream_chunk_logged = False
        playful_messages = [
            "Pulling out the best insights",
            "Connecting the dots",
            "Highlighting the sharpest moments",
            "Building your action list",
            "Polishing the key takeaways",
            "Shaping the final narrative",
        ]
        message_index = 0

        stream_failed = False
        try:
            async for delta in stream_summarize_transcript(transcript_text, settings.openrouter_api_key):
                summary_markdown += delta
                if not first_stream_chunk_logged:
                    _log_stage(
                        "worker.summary.first_stream_chunk",
                        job_start=job_start,
                        stage="summarizing",
                        provider="openrouter",
                        model=OPENROUTER_MODEL,
                        chunk_chars=len(delta),
                        level=logging.DEBUG,
                    )
                    first_stream_chunk_logged = True
                should_flush = False
                if len(summary_markdown) - last_flush_len >= STREAM_FLUSH_CHAR_THRESHOLD:
                    should_flush = True
                if time.monotonic() - last_flush_time >= STREAM_FLUSH_SECONDS:
                    should_flush = True

                if should_flush:
                    await update_summary_markdown(
                        admin_client,
                        summary_id=summary_id,
                        summary_markdown=summary_markdown,
                    )
                    flush_count += 1
                    last_flush_len = len(summary_markdown)
                    last_flush_time = time.monotonic()
                    if not first_visible_logged:
                        _log_stage(
                            "worker.summary.first_markdown_persisted",
                            job_start=job_start,
                            stage="summarizing",
                            provider="openrouter",
                            model=OPENROUTER_MODEL,
                            chars=len(summary_markdown),
                            flush_count=flush_count,
                        )
                        await record_timeline_event(
                            admin_client,
                            logger,
                            job_id=job_id,
                            event_type="first_markdown_persisted",
                            stage="summarizing",
                            message="First briefing text persisted.",
                            metadata={
                                "summary_id": summary_id,
                                "markdown_chars": len(summary_markdown),
                                "flush_count": flush_count,
                            },
                        )
                        first_visible_logged = True
                    progress = min(progress + 1, 92)
                    await update_job_progress(
                        admin_client,
                        job_id=job_id,
                        stage="summarizing",
                        progress=progress,
                        status_message=playful_messages[message_index % len(playful_messages)],
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
            fallback_start = time.perf_counter()
            logger.warning(
                "worker.summary.fallback.started",
                extra={
                    "elapsed_ms": elapsed_ms(job_start),
                    "stage": "summarizing",
                    "provider": "openrouter",
                    "model": OPENROUTER_MODEL,
                    "stream_failed": stream_failed,
                    "streamed_chars": len(summary_markdown),
                    "flush_count": flush_count,
                },
            )
            await record_timeline_event(
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
                    "streamed_chars": len(summary_markdown),
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
            summary_markdown = await summarize_transcript(transcript_text, settings.openrouter_api_key)
            _log_step(
                "worker.summary.fallback.completed",
                duration_ms=(time.perf_counter() - fallback_start) * 1000,
                stage="summarizing",
                provider="openrouter",
                model=OPENROUTER_MODEL,
                markdown_chars=len(summary_markdown),
            )

        if summary_markdown:
            await update_summary_markdown(
                admin_client,
                summary_id=summary_id,
                summary_markdown=summary_markdown,
            )
            if not first_visible_logged:
                _log_stage(
                    "worker.summary.first_markdown_persisted",
                    job_start=job_start,
                    stage="summarizing",
                    provider="openrouter",
                    model=OPENROUTER_MODEL,
                    chars=len(summary_markdown),
                    flush_count=flush_count,
                )
                await record_timeline_event(
                    admin_client,
                    logger,
                    job_id=job_id,
                    event_type="first_markdown_persisted",
                    stage="summarizing",
                    message="First briefing text persisted.",
                    metadata={
                        "summary_id": summary_id,
                        "markdown_chars": len(summary_markdown),
                        "flush_count": flush_count,
                    },
                )
                first_visible_logged = True

        _log_step(
            "worker.summary.completed",
            duration_ms=(time.perf_counter() - step_start) * 1000,
            stage="summarizing",
            provider="openrouter",
            model=OPENROUTER_MODEL,
            markdown_chars=len(summary_markdown),
            flush_count=flush_count,
            fallback_used=stream_failed,
        )
        await record_timeline_event(
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
                "markdown_chars": len(summary_markdown),
                "flush_count": flush_count,
                "fallback_used": stream_failed,
                "duration_ms": round((time.perf_counter() - step_start) * 1000, 2),
            },
        )

        _log_stage(
            "worker.stage.started",
            job_start=job_start,
            stage="finalizing",
            summary_id=summary_id,
            markdown_chars=len(summary_markdown),
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
        try:
            await record_usage_for_job(
                user_id=user_id,
                job_id=job_id,
                duration_seconds=job.get("duration_seconds"),
                settings=settings,
            )
        except Exception:
            logger.exception("worker.usage_recording.failed", extra={"job_id": job_id, "cache_hit": False})
        _log_step(
            "worker.job.completed",
            duration_ms=(time.perf_counter() - job_start) * 1000,
            cache_hit=False,
            stage="completed",
            provider="openrouter",
            model=OPENROUTER_MODEL,
            markdown_chars=len(summary_markdown),
            flush_count=flush_count,
        )
        await record_timeline_event(
            admin_client,
            logger,
            job_id=job_id,
            event_type="job_completed",
            stage="completed",
            message="Briefing ready.",
            metadata={
                "cache_hit": False,
                "duration_ms": round((time.perf_counter() - job_start) * 1000, 2),
                "summary_id": summary_id,
                "markdown_chars": len(summary_markdown),
                "flush_count": flush_count,
            },
        )


async def _handle_claimed_job(
    job: dict[str, Any],
    settings: Settings,
    admin_client: AsyncClient,
) -> None:
    attempt_count = int(job.get("attempt_count") or 0)
    job_id = job.get("id")
    if not job_id:
        logger.debug("worker.job.claim_empty")
        return

    logger.debug(
        "worker.job.claimed",
        extra={
            "job_id": job_id,
            "attempt": attempt_count,
            "user_id": job.get("user_id"),
            "url_host": urlparse(str(job.get("url") or "")).netloc.lower(),
        },
    )
    await record_timeline_event(
        admin_client,
        logger,
        job_id=str(job_id),
        event_type="job_claimed",
        stage="running",
        message="Worker claimed the job.",
        metadata={
            "attempt": attempt_count,
            "user_id": job.get("user_id"),
            "url_host": urlparse(str(job.get("url") or "")).netloc.lower(),
        },
    )
    if not job.get("url") or not job.get("user_id"):
        error_message = "Job is missing required fields (url or user_id)."
        logger.error("worker.job.invalid_payload", extra={"job_id": job_id})
        await record_timeline_event(
            admin_client,
            logger,
            job_id=str(job_id),
            event_type="job_failed",
            stage="failed",
            message=error_message,
            metadata={"attempt": attempt_count, "error_code": "invalid_job_payload", "will_retry": False},
        )
        await mark_job_failed(
            admin_client,
            job_id=job_id,
            error_code="invalid_job_payload",
            error_message=error_message,
        )
        return

    if attempt_count > WORKER_MAX_ATTEMPTS:
        error_message = "Job exceeded maximum retry attempts."
        await record_timeline_event(
            admin_client,
            logger,
            job_id=str(job_id),
            event_type="job_failed",
            stage="failed",
            message=error_message,
            metadata={"attempt": attempt_count, "error_code": "max_attempts_exceeded", "will_retry": False},
        )
        await mark_job_failed(
            admin_client,
            job_id=job_id,
            error_code="max_attempts_exceeded",
            error_message=error_message,
        )
        return

    attempt_start = time.perf_counter()
    try:
        with log_context(job_id=job_id, attempt=attempt_count):
            await _process_job(job, settings, admin_client)
    except Exception as exc:
        error_code, error_message = extract_job_error(exc)
        await record_timeline_event(
            admin_client,
            logger,
            job_id=str(job_id),
            event_type="job_failed",
            stage="failed",
            message=error_message,
            metadata={
                "attempt": attempt_count,
                "duration_ms": elapsed_ms(attempt_start),
                "error_code": error_code,
                "will_retry": attempt_count < WORKER_MAX_ATTEMPTS,
            },
        )
        logger.exception(
            "worker.job.failed",
            extra={
                "job_id": job_id,
                "attempt": attempt_count,
                "duration_ms": elapsed_ms(attempt_start),
                "error_code": error_code,
                "will_retry": attempt_count < WORKER_MAX_ATTEMPTS,
            },
        )
        if attempt_count < WORKER_MAX_ATTEMPTS:
            backoff_seconds = _compute_backoff_seconds(WORKER_BACKOFF_BASE_SECONDS, attempt_count)
            run_after = datetime.now(UTC) + timedelta(seconds=backoff_seconds)
            await mark_job_retry(
                admin_client,
                job_id=job_id,
                error_code=error_code,
                error_message=error_message,
                run_after=run_after,
            )
        else:
            await mark_job_failed(
                admin_client,
                job_id=job_id,
                error_code=error_code,
                error_message=error_message,
            )


async def _wait_for_job_notification(
    queue: asyncio.Queue[dict[str, Any]],
    *,
    timeout_seconds: float,
) -> bool:
    try:
        payload = await asyncio.wait_for(queue.get(), timeout=timeout_seconds)
        return payload is not None
    except TimeoutError:
        return False
    except Exception as exc:
        logger.warning("worker.job_notification.listen_failed", exc_info=exc)
        return False


def _drain_completed_tasks(tasks: set[asyncio.Task[None]]) -> None:
    done_tasks = {task for task in tasks if task.done()}
    for task in done_tasks:
        tasks.remove(task)
        try:
            task.result()
        except Exception:
            logger.exception("worker.task.crashed")


async def _run_scheduled_maintenance(
    admin_client: AsyncClient,
    *,
    settings: Settings,
    last_sweep_at: float,
    last_billing_maintenance_at: float,
) -> tuple[float, float]:
    now = time.monotonic()
    if now - last_sweep_at >= WORKER_SWEEP_INTERVAL_SECONDS:
        requeued_jobs = await requeue_stale_jobs(admin_client, stale_after_seconds=WORKER_STALE_AFTER_SECONDS)
        log_level = logging.INFO if requeued_jobs else logging.DEBUG
        logger.log(
            log_level,
            "worker.stale_job_sweep.completed",
            extra={
                "stale_after_seconds": WORKER_STALE_AFTER_SECONDS,
                "requeued_jobs": requeued_jobs,
            },
        )
        last_sweep_at = now

    if now - last_billing_maintenance_at >= WORKER_BILLING_MAINTENANCE_INTERVAL_SECONDS:
        await run_billing_maintenance(admin_client, settings=settings)
        last_billing_maintenance_at = now

    return last_sweep_at, last_billing_maintenance_at


async def _run_loop(settings: Settings) -> None:
    admin_client = await create_supabase_admin_client(settings)
    max_concurrent_jobs = max(1, settings.worker_max_concurrent_jobs)
    notify_timeout_seconds = WORKER_JOB_NOTIFY_TIMEOUT_SECONDS
    running_tasks: set[asyncio.Task[None]] = set()
    last_sweep_at = 0.0
    last_billing_maintenance_at = 0.0

    while True:
        try:
            async with listen_for_notifications(settings, "job_created") as queue:
                logger.info("worker.job_listener.ready", extra={"channel": "job_created"})
                while True:
                    _drain_completed_tasks(running_tasks)
                    last_sweep_at, last_billing_maintenance_at = await _run_scheduled_maintenance(
                        admin_client,
                        settings=settings,
                        last_sweep_at=last_sweep_at,
                        last_billing_maintenance_at=last_billing_maintenance_at,
                    )
                    while len(running_tasks) < max_concurrent_jobs:
                        job = await claim_next_job(admin_client)
                        if not job:
                            break

                        task = asyncio.create_task(_handle_claimed_job(job, settings, admin_client))
                        running_tasks.add(task)

                    if running_tasks:
                        await asyncio.sleep(WORKER_IDLE_SLEEP_SECONDS)
                        continue

                    if await _wait_for_job_notification(queue, timeout_seconds=notify_timeout_seconds):
                        continue

                    await asyncio.sleep(WORKER_IDLE_SLEEP_SECONDS)
        except Exception:
            logger.warning("worker.job_listener.reconnecting", extra={"channel": "job_created"}, exc_info=True)
            await asyncio.sleep(WORKER_IDLE_SLEEP_SECONDS)


def main() -> None:
    setup_logging(service="worker")
    settings = get_settings()
    logger.info(
        "worker.started",
        extra={"max_concurrent_jobs": settings.worker_max_concurrent_jobs},
    )
    asyncio.run(_run_loop(settings))


if __name__ == "__main__":
    main()

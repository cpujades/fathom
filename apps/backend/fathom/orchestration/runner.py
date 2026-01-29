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

from fathom.core.config import Settings, get_settings
from fathom.core.constants import SUMMARY_PROMPT_KEY_DEFAULT
from fathom.core.errors import AppError
from fathom.core.logging import log_context
from fathom.crud.supabase.jobs import (
    claim_next_job,
    mark_job_failed,
    mark_job_retry,
    mark_job_succeeded,
    requeue_stale_jobs,
    update_job_progress,
)
from fathom.crud.supabase.summaries import create_summary, fetch_summary_by_keys, update_summary_markdown
from fathom.crud.supabase.transcripts import (
    create_transcript,
    fetch_transcript_by_hash,
    fetch_transcript_by_video_id,
)
from fathom.services.downloader import download_audio, fetch_muxed_media_url
from fathom.services.summarizer import OPENROUTER_MODEL, stream_summarize_transcript, summarize_transcript
from fathom.services.supabase import create_supabase_admin_client
from fathom.services.transcriber import DEEPGRAM_MODEL, transcribe_file, transcribe_url
from fathom.services.youtube import extract_youtube_video_id
from supabase import AsyncClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Worker configuration
# ---------------------------------------------------------------------------
WORKER_POLL_INTERVAL_SECONDS = 2
WORKER_IDLE_SLEEP_SECONDS = 1
WORKER_MAX_ATTEMPTS = 3
WORKER_BACKOFF_BASE_SECONDS = 5
WORKER_STALE_AFTER_SECONDS = 900  # 15 minutes

# Direct URL transcription configuration
DIRECT_URL_MAX_ATTEMPTS = 2

# Streaming summary flush tuning
STREAM_FLUSH_CHAR_THRESHOLD = 400
STREAM_FLUSH_SECONDS = 2.5


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _compute_backoff_seconds(base: int, attempt: int) -> int:
    return int(base * (2 ** max(attempt - 1, 0)))


def _log_step(label: str, *, duration_ms: float, **fields: object) -> None:
    field_text = " ".join(f"{key}={value}" for key, value in fields.items())
    if field_text:
        logger.info("%s %.2fms %s", label, duration_ms, field_text)
    else:
        logger.info("%s %.2fms", label, duration_ms)


async def _resolve_transcript(
    *,
    url: str,
    settings: Settings,
    admin_client: AsyncClient,
) -> tuple[str, str, str | None]:
    """Return (transcript_id, transcript_text, video_id_or_hash)."""
    url_hash = _hash_url(url)
    parsed_url = urlparse(url)
    parsed_video_id = extract_youtube_video_id(parsed_url)
    transcript_text: str
    video_id: str | None = None
    provider_model = f"deepgram:{DEEPGRAM_MODEL}"

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
        logger.info("transcript cache_hit=true transcript_id=%s video_id=%s", transcript_id, video_id)
        return transcript_id, transcript_text, video_id or url_hash

    direct_url: str | None
    try:
        direct_url = await asyncio.to_thread(fetch_muxed_media_url, url)
    except Exception:
        direct_url = None

    direct_transcription_succeeded = False
    if direct_url:
        for attempt in range(1, DIRECT_URL_MAX_ATTEMPTS + 1):
            step_start = time.perf_counter()
            try:
                transcript_text = await transcribe_url(direct_url, settings.deepgram_api_key)
                _log_step(
                    "transcribe_url",
                    duration_ms=(time.perf_counter() - step_start) * 1000,
                    provider="deepgram",
                    attempt=attempt,
                )
                video_id = parsed_video_id
                direct_transcription_succeeded = True
                break
            except Exception as exc:  # Fall back to download on any failure.
                duration_ms = (time.perf_counter() - step_start) * 1000
                logger.warning(
                    "transcribe_url failed attempt=%s %.2fms error=%s",
                    attempt,
                    duration_ms,
                    type(exc).__name__,
                )

    if not direct_transcription_succeeded:
        with tempfile.TemporaryDirectory() as tmp_dir:
            step_start = time.perf_counter()
            download_result = await asyncio.to_thread(download_audio, url, tmp_dir)
            _log_step(
                "download_audio",
                duration_ms=(time.perf_counter() - step_start) * 1000,
                video_id=download_result.video_id or parsed_video_id,
            )
            video_id = download_result.video_id or parsed_video_id
            step_start = time.perf_counter()
            transcript_text = await transcribe_file(download_result.path, settings.deepgram_api_key)
            _log_step(
                "transcribe_file",
                duration_ms=(time.perf_counter() - step_start) * 1000,
                provider="deepgram",
            )

    transcript_row = await create_transcript(
        admin_client,
        url_hash=url_hash,
        video_id=video_id,
        transcript_text=transcript_text,
        provider_model=provider_model,
    )
    transcript_id = transcript_row["id"]
    return transcript_id, transcript_text, video_id or url_hash


async def _process_job(job: dict[str, Any], settings: Settings, admin_client: AsyncClient) -> None:
    job_id = job["id"]
    url = job["url"]
    user_id = job["user_id"]
    requested_summary_id = str(uuid.uuid4())
    job_start = time.perf_counter()

    with log_context(job_id=job_id, user_id=user_id, summary_id=requested_summary_id):
        logger.info("job start")
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
            url=url,
            settings=settings,
            admin_client=admin_client,
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
        if cached_summary:
            cached_summary_id = cached_summary["id"]
            logger.info("summary cache_hit=true summary_id=%s", cached_summary_id)
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
            _log_step(
                "job complete (cached summary)",
                duration_ms=(time.perf_counter() - job_start) * 1000,
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
                    last_flush_len = len(summary_markdown)
                    last_flush_time = time.monotonic()
                    progress = min(progress + 3, 92)
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

        if stream_failed or not summary_markdown.strip():
            await update_job_progress(
                admin_client,
                job_id=job_id,
                stage="summarizing",
                progress=min(progress + 5, 92),
                status_message="Finalizing a full summary",
            )
            summary_markdown = await summarize_transcript(transcript_text, settings.openrouter_api_key)

        if summary_markdown:
            await update_summary_markdown(
                admin_client,
                summary_id=summary_id,
                summary_markdown=summary_markdown,
            )

        _log_step(
            "summarize_transcript",
            duration_ms=(time.perf_counter() - step_start) * 1000,
            model=OPENROUTER_MODEL,
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
        _log_step(
            "job complete",
            duration_ms=(time.perf_counter() - job_start) * 1000,
        )


def _extract_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, AppError):
        return exc.code, exc.detail
    return "internal_error", str(exc) or "Unhandled error."


async def _run_loop(settings: Settings) -> None:
    admin_client = await create_supabase_admin_client(settings)

    while True:
        await requeue_stale_jobs(admin_client, stale_after_seconds=WORKER_STALE_AFTER_SECONDS)
        job = await claim_next_job(admin_client)
        if not job:
            await asyncio.sleep(WORKER_IDLE_SLEEP_SECONDS)
            continue

        attempt_count = int(job.get("attempt_count") or 0)
        job_id = job.get("id")
        if not job_id:
            logger.debug("claim_next_job returned an empty row; treating as no job available")
            await asyncio.sleep(WORKER_IDLE_SLEEP_SECONDS)
            continue

        logger.info("job claimed job_id=%s attempt=%s", job_id, attempt_count)
        if not job.get("url") or not job.get("user_id"):
            logger.error("job missing required fields job_id=%s", job_id)
            await mark_job_failed(
                admin_client,
                job_id=job_id,
                error_code="invalid_job_payload",
                error_message="Job is missing required fields (url or user_id).",
            )
            await asyncio.sleep(WORKER_POLL_INTERVAL_SECONDS)
            continue

        if attempt_count > WORKER_MAX_ATTEMPTS:
            await mark_job_failed(
                admin_client,
                job_id=job_id,
                error_code="max_attempts_exceeded",
                error_message="Job exceeded maximum retry attempts.",
            )
            await asyncio.sleep(WORKER_POLL_INTERVAL_SECONDS)
            continue

        try:
            with log_context(job_id=job_id, attempt=attempt_count):
                await _process_job(job, settings, admin_client)
        except Exception as exc:
            error_code, error_message = _extract_error(exc)
            logger.exception(
                "job failed job_id=%s attempt=%s error_code=%s",
                job_id,
                attempt_count,
                error_code,
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

        await asyncio.sleep(WORKER_POLL_INTERVAL_SECONDS)


def main() -> None:
    settings = get_settings()
    logger.info("Starting worker loop")
    asyncio.run(_run_loop(settings))


if __name__ == "__main__":
    main()

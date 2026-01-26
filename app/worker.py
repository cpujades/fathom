from __future__ import annotations

import asyncio
import hashlib
import logging
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from app.core.config import Settings, get_settings
from app.core.constants import SUMMARY_PROMPT_KEY_DEFAULT
from app.core.errors import AppError
from app.crud.supabase.jobs import (
    claim_next_job,
    mark_job_failed,
    mark_job_retry,
    mark_job_succeeded,
    requeue_stale_jobs,
)
from app.crud.supabase.summaries import create_summary
from app.crud.supabase.transcripts import (
    create_transcript,
    fetch_transcript_by_hash,
    fetch_transcript_by_video_id,
)
from app.services.downloader import download_audio, fetch_muxed_media_url
from app.services.summarizer import summarize_transcript
from app.services.supabase import create_supabase_admin_client
from app.services.transcriber import TranscriptionError, transcribe_file, transcribe_url
from app.services.youtube import extract_youtube_video_id
from supabase import AsyncClient

logger = logging.getLogger("fathom.worker")


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _compute_backoff_seconds(base: int, attempt: int) -> int:
    return int(base * (2 ** max(attempt - 1, 0)))


async def _run_pipeline(
    *,
    url: str,
    settings: Settings,
    provider_model: str,
    admin_client: AsyncClient,
) -> tuple[str, str, str | None]:
    url_hash = _hash_url(url)
    parsed_url = urlparse(url)
    parsed_video_id = extract_youtube_video_id(parsed_url)
    transcript_text: str
    video_id: str | None = None

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
    else:
        direct_url = None
        try:
            direct_url = await asyncio.to_thread(fetch_muxed_media_url, url)
        except Exception:
            direct_url = None

        if direct_url:
            try:
                transcript_text = await transcribe_url(direct_url, settings.deepgram_api_key, settings.deepgram_model)
                video_id = parsed_video_id
            except TranscriptionError:
                direct_url = None

        if not direct_url:
            with tempfile.TemporaryDirectory() as tmp_dir:
                download_result = await asyncio.to_thread(download_audio, url, tmp_dir)
                video_id = download_result.video_id or parsed_video_id
                transcript_text = await transcribe_file(
                    download_result.path, settings.deepgram_api_key, settings.deepgram_model
                )

        transcript_row = await create_transcript(
            admin_client,
            url_hash=url_hash,
            video_id=video_id,
            transcript_text=transcript_text,
            provider_model=provider_model,
        )
        transcript_id = transcript_row["id"]

    summary_markdown = await asyncio.to_thread(
        summarize_transcript,
        transcript_text,
        settings.openrouter_api_key,
        settings.openrouter_model,
        settings.openrouter_site_url,
        settings.openrouter_app_name,
    )
    return transcript_id, summary_markdown, video_id or url_hash


async def _process_job(job: dict[str, Any], settings: Settings, admin_client: AsyncClient) -> None:
    job_id = job["id"]
    url = job["url"]
    user_id = job["user_id"]

    provider_model = "deepgram:nova-2"
    summary_id = str(uuid.uuid4())

    transcript_id, summary_markdown, video_segment = await _run_pipeline(
        url=url,
        settings=settings,
        provider_model=provider_model,
        admin_client=admin_client,
    )

    await create_summary(
        admin_client,
        summary_id=summary_id,
        user_id=user_id,
        transcript_id=transcript_id,
        prompt_key=SUMMARY_PROMPT_KEY_DEFAULT,
        summary_model=settings.openrouter_model,
        summary_markdown=summary_markdown,
        pdf_object_key=None,
    )

    await mark_job_succeeded(admin_client, job_id=job_id, summary_id=summary_id)


def _extract_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, AppError):
        return exc.code, exc.detail
    return "internal_error", str(exc) or "Unhandled error."


async def _run_loop(settings: Settings) -> None:
    idle_sleep = settings.worker_idle_sleep_seconds
    poll_interval = settings.worker_poll_interval_seconds
    max_attempts = settings.worker_max_attempts
    backoff_base = settings.worker_backoff_base_seconds
    stale_after = settings.worker_stale_after_seconds

    admin_client = await create_supabase_admin_client(settings)

    while True:
        await requeue_stale_jobs(admin_client, stale_after_seconds=stale_after)
        job = await claim_next_job(admin_client)
        if not job:
            await asyncio.sleep(idle_sleep)
            continue

        attempt_count = int(job.get("attempt_count") or 0)
        if attempt_count > max_attempts:
            await mark_job_failed(
                admin_client,
                job_id=job["id"],
                error_code="max_attempts_exceeded",
                error_message="Job exceeded maximum retry attempts.",
            )
            await asyncio.sleep(poll_interval)
            continue

        try:
            await _process_job(job, settings, admin_client)
        except Exception as exc:
            error_code, error_message = _extract_error(exc)
            if attempt_count < max_attempts:
                backoff_seconds = _compute_backoff_seconds(backoff_base, attempt_count)
                run_after = datetime.now(UTC) + timedelta(seconds=backoff_seconds)
                await mark_job_retry(
                    admin_client,
                    job_id=job["id"],
                    error_code=error_code,
                    error_message=error_message,
                    run_after=run_after,
                )
            else:
                await mark_job_failed(
                    admin_client,
                    job_id=job["id"],
                    error_code=error_code,
                    error_message=error_message,
                )

        await asyncio.sleep(poll_interval)


def main() -> None:
    settings = get_settings()
    logger.info("Starting worker loop")
    asyncio.run(_run_loop(settings))


if __name__ == "__main__":
    main()

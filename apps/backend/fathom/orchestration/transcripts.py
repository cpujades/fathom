from __future__ import annotations

import asyncio
import hashlib
import logging
import tempfile
import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

from fathom.core.config import Settings
from fathom.core.constants import GROQ_MODEL, GROQ_SIGNED_URL_TTL_SECONDS, SUPABASE_GROQ_BUCKET
from fathom.crud.supabase.job_events import record_job_event_best_effort
from fathom.crud.supabase.storage_objects import create_signed_url, delete_object, upload_object
from fathom.crud.supabase.transcripts import (
    create_transcript,
    fetch_transcript_by_hash,
    fetch_transcript_by_video_id,
)
from fathom.orchestration.observability import log_stage, log_step
from fathom.services.downloader import download_audio
from fathom.services.transcriber import transcribe_url
from fathom.services.youtube import extract_youtube_video_id
from supabase import AsyncClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscriptResolution:
    transcript_id: str
    transcript_text: str
    source_key: str


async def resolve_transcript(
    *,
    job_id: str,
    url: str,
    settings: Settings,
    admin_client: AsyncClient,
    job_start: float,
) -> TranscriptResolution:
    url_hash = _hash_url(url)
    parsed_video_id = extract_youtube_video_id(urlparse(url))
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
        return await _cached_resolution(
            job_id=job_id,
            admin_client=admin_client,
            job_start=job_start,
            transcript_row=transcript_row,
            parsed_video_id=parsed_video_id,
            url_hash=url_hash,
        )

    return await _create_transcript(
        job_id=job_id,
        url=url,
        settings=settings,
        admin_client=admin_client,
        job_start=job_start,
        parsed_video_id=parsed_video_id,
        url_hash=url_hash,
        provider_model=provider_model,
    )


async def _cached_resolution(
    *,
    job_id: str,
    admin_client: AsyncClient,
    job_start: float,
    transcript_row: dict[str, object],
    parsed_video_id: str | None,
    url_hash: str,
) -> TranscriptResolution:
    transcript_text = str(transcript_row["transcript_text"])
    video_id = transcript_row.get("video_id") or parsed_video_id
    transcript_id = str(transcript_row["id"])
    log_stage(
        logger,
        "worker.transcript.cache_hit",
        job_start=job_start,
        stage="transcribing",
        provider="groq",
        model=GROQ_MODEL,
        transcript_id=transcript_id,
        video_id=video_id,
        transcript_chars=len(transcript_text),
    )
    await record_job_event_best_effort(
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
    return TranscriptResolution(
        transcript_id=transcript_id,
        transcript_text=transcript_text,
        source_key=str(video_id or url_hash),
    )


async def _create_transcript(
    *,
    job_id: str,
    url: str,
    settings: Settings,
    admin_client: AsyncClient,
    job_start: float,
    parsed_video_id: str | None,
    url_hash: str,
    provider_model: str,
) -> TranscriptResolution:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_stage(
            logger,
            "worker.audio.download.started",
            job_start=job_start,
            stage="transcribing",
            video_id=parsed_video_id,
            level=logging.DEBUG,
        )
        download_start = time.perf_counter()
        download_result = await asyncio.to_thread(download_audio, url, tmp_dir)
        download_duration_ms = (time.perf_counter() - download_start) * 1000
        log_step(
            logger,
            "worker.audio.downloaded",
            duration_ms=download_duration_ms,
            stage="transcribing",
            video_id=parsed_video_id,
            bytes=download_result.filesize_bytes,
        )
        video_id = download_result.video_id or parsed_video_id
        await record_job_event_best_effort(
            admin_client,
            logger,
            job_id=job_id,
            event_type="source_downloaded",
            stage="transcribing",
            message="Source audio downloaded.",
            metadata={
                "video_id": video_id,
                "bytes": download_result.filesize_bytes,
                "duration_ms": round(download_duration_ms, 2),
            },
        )

        object_key = f"groq-audio/{uuid.uuid4().hex}.{download_result.subtype or 'bin'}"
        audio_bytes = await asyncio.to_thread(download_result.path.read_bytes)
        await upload_object(
            admin_client,
            bucket=SUPABASE_GROQ_BUCKET,
            object_key=object_key,
            data=audio_bytes,
            content_type=download_result.mime_type or "application/octet-stream",
        )
        try:
            transcript_text = await _transcribe_uploaded_audio(
                job_id=job_id,
                settings=settings,
                admin_client=admin_client,
                job_start=job_start,
                object_key=object_key,
                audio_bytes=download_result.filesize_bytes,
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
    transcript_id = str(transcript_row["id"])
    log_stage(
        logger,
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
    await record_job_event_best_effort(
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
    return TranscriptResolution(
        transcript_id=transcript_id,
        transcript_text=transcript_text,
        source_key=str(video_id or url_hash),
    )


async def _transcribe_uploaded_audio(
    *,
    job_id: str,
    settings: Settings,
    admin_client: AsyncClient,
    job_start: float,
    object_key: str,
    audio_bytes: int | None,
) -> str:
    signed_url = await create_signed_url(
        admin_client,
        bucket=SUPABASE_GROQ_BUCKET,
        object_key=object_key,
        ttl_seconds=GROQ_SIGNED_URL_TTL_SECONDS,
    )
    log_stage(
        logger,
        "worker.transcription.provider.started",
        job_start=job_start,
        stage="transcribing",
        provider="groq",
        model=GROQ_MODEL,
        audio_bytes=audio_bytes,
        level=logging.DEBUG,
    )
    await record_job_event_best_effort(
        admin_client,
        logger,
        job_id=job_id,
        event_type="transcription_started",
        stage="transcribing",
        message="Transcription provider started.",
        metadata={"provider": "groq", "model": GROQ_MODEL, "audio_bytes": audio_bytes},
    )

    started_at = time.perf_counter()
    transcript_text = await asyncio.to_thread(
        transcribe_url,
        signed_url,
        settings.groq_api_key,
        GROQ_MODEL,
    )
    duration_ms = (time.perf_counter() - started_at) * 1000
    log_step(
        logger,
        "worker.transcript.created",
        duration_ms=duration_ms,
        stage="transcribing",
        provider="groq",
        model=GROQ_MODEL,
        transcript_chars=len(transcript_text),
    )
    await record_job_event_best_effort(
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
            "duration_ms": round(duration_ms, 2),
        },
    )
    return transcript_text


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()

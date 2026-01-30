from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from dataclasses import dataclass

from fathom.core.config import Settings
from fathom.core.constants import GROQ_MODEL, GROQ_SIGNED_URL_TTL_SECONDS, SUPABASE_GROQ_BUCKET
from fathom.core.logging import log_context
from fathom.crud.supabase.storage_objects import create_signed_url, delete_object, upload_object
from fathom.services.downloader import download_audio
from fathom.services.pdf import markdown_to_pdf_bytes
from fathom.services.summarizer import summarize_transcript
from fathom.services.supabase import create_supabase_admin_client
from fathom.services.transcriber import transcribe_url


@dataclass(frozen=True)
class PipelineResult:
    summary_id: str
    markdown: str
    pdf_bytes: bytes


logger = logging.getLogger(__name__)


async def run_pipeline(summary_id: str, url: str, settings: Settings) -> PipelineResult:
    with log_context(summary_id=summary_id):
        with tempfile.TemporaryDirectory() as tmp_dir:
            step_start = time.perf_counter()
            download_result = await asyncio.to_thread(download_audio, url, tmp_dir)
            logger.info(
                "download_audio %.2fms bytes=%s",
                (time.perf_counter() - step_start) * 1000,
                download_result.filesize_bytes,
            )

            admin_client = await create_supabase_admin_client(settings)
            object_key = f"groq-audio/{summary_id}.{download_result.subtype or 'bin'}"
            audio_bytes = await asyncio.to_thread(download_result.path.read_bytes)
            await upload_object(
                admin_client,
                bucket=SUPABASE_GROQ_BUCKET,
                object_key=object_key,
                data=audio_bytes,
                content_type=download_result.mime_type or "application/octet-stream",
            )
            try:
                signed_url = await create_signed_url(
                    admin_client,
                    bucket=SUPABASE_GROQ_BUCKET,
                    object_key=object_key,
                    ttl_seconds=GROQ_SIGNED_URL_TTL_SECONDS,
                )
                step_start = time.perf_counter()
                transcript = await asyncio.to_thread(
                    transcribe_url,
                    signed_url,
                    settings.groq_api_key,
                    GROQ_MODEL,
                )
                logger.info(
                    "transcribe_url %.2fms",
                    (time.perf_counter() - step_start) * 1000,
                )
            finally:
                try:
                    await delete_object(
                        admin_client,
                        bucket=SUPABASE_GROQ_BUCKET,
                        object_key=object_key,
                    )
                except Exception:
                    logger.warning("failed to cleanup groq audio object", exc_info=True)

        step_start = time.perf_counter()
        markdown = await summarize_transcript(transcript, settings.openrouter_api_key)
        logger.info(
            "summarize_transcript %.2fms",
            (time.perf_counter() - step_start) * 1000,
        )

        step_start = time.perf_counter()
        pdf_bytes = await asyncio.to_thread(markdown_to_pdf_bytes, markdown)
        logger.info(
            "render_pdf %.2fms",
            (time.perf_counter() - step_start) * 1000,
        )

        return PipelineResult(summary_id=summary_id, markdown=markdown, pdf_bytes=pdf_bytes)

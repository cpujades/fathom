from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from dataclasses import dataclass

from app.core.config import Settings
from app.core.logging import log_context
from app.services.downloader import download_audio
from app.services.pdf import markdown_to_pdf_bytes
from app.services.summarizer import summarize_transcript
from app.services.transcriber import transcribe_file


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
                "download_audio %.2fms video_id=%s",
                (time.perf_counter() - step_start) * 1000,
                download_result.video_id,
            )
            step_start = time.perf_counter()
            transcript = await transcribe_file(download_result.path, settings.deepgram_api_key)
            logger.info(
                "transcribe_file %.2fms",
                (time.perf_counter() - step_start) * 1000,
            )

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

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass

from app.core.config import Settings
from app.services.downloader import download_audio
from app.services.pdf import markdown_to_pdf_bytes
from app.services.summarizer import summarize_transcript
from app.services.transcriber import transcribe_file


@dataclass(frozen=True)
class PipelineResult:
    summary_id: str
    markdown: str
    pdf_bytes: bytes


async def run_pipeline(summary_id: str, url: str, settings: Settings) -> PipelineResult:
    with tempfile.TemporaryDirectory() as tmp_dir:
        download_result = await asyncio.to_thread(download_audio, url, tmp_dir)
        transcript = await transcribe_file(download_result.path, settings.deepgram_api_key)

    markdown = await summarize_transcript(transcript, settings.openrouter_api_key)

    pdf_bytes = await asyncio.to_thread(markdown_to_pdf_bytes, markdown)

    return PipelineResult(summary_id=summary_id, markdown=markdown, pdf_bytes=pdf_bytes)

from __future__ import annotations

import pathlib
from dataclasses import dataclass

from app.core.config import Settings
from app.services.downloader import download_audio
from app.services.pdf import markdown_to_pdf
from app.services.summarizer import summarize_transcript
from app.services.transcriber import transcribe_file


@dataclass(frozen=True)
class PipelineResult:
    summary_id: str
    markdown: str
    pdf_path: pathlib.Path


def run_pipeline(summary_id: str, url: str, settings: Settings) -> PipelineResult:
    output_dir = pathlib.Path(settings.output_dir)

    audio_path = download_audio(url, str(output_dir))
    transcript = transcribe_file(audio_path, settings.deepgram_api_key)
    markdown = summarize_transcript(
        transcript,
        settings.openrouter_api_key,
        settings.openrouter_model,
        settings.openrouter_site_url,
        settings.openrouter_app_name,
    )
    markdown_path = output_dir / f"{summary_id}.md"
    markdown_path.write_text(markdown, encoding="utf-8")
    pdf_path = output_dir / f"{summary_id}.pdf"
    markdown_to_pdf(markdown, pdf_path)

    return PipelineResult(summary_id=summary_id, markdown=markdown, pdf_path=pdf_path)

from __future__ import annotations

import os
import pathlib
import uuid

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.core.errors import InvalidRequestError, NotFoundError
from app.pipeline import run_pipeline
from app.schemas.errors import ErrorResponse
from app.schemas.summaries import SummarizeRequest, SummarizeResponse
from app.validators import validate_summary_id

router = APIRouter()


@router.post(
    "/summarize",
    response_model=SummarizeResponse,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Invalid input (e.g., malformed URL, invalid summary id).",
        },
        502: {
            "model": ErrorResponse,
            "description": "Upstream provider failed (Deepgram/OpenRouter/yt-dlp).",
        },
        500: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
)
def summarize(request: SummarizeRequest) -> SummarizeResponse:
    settings = get_settings()
    summary_id = uuid.uuid4().hex

    result = run_pipeline(summary_id, str(request.url), settings)

    return SummarizeResponse(
        summary_id=result.summary_id,
        markdown=result.markdown,
        pdf_url=f"/summaries/{result.summary_id}.pdf",
    )


@router.get(
    "/summaries/{summary_id}.pdf",
    response_class=FileResponse,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Invalid summary id.",
        },
        404: {
            "model": ErrorResponse,
            "description": "PDF not found.",
        },
        500: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
)
def get_pdf(summary_id: str) -> FileResponse:
    validate_summary_id(summary_id)
    settings = get_settings()
    output_dir = pathlib.Path(settings.output_dir).resolve()
    pdf_path = (output_dir / f"{summary_id}.pdf").resolve()

    # Defense-in-depth: ensure user input can't escape OUTPUT_DIR even if validation changes.
    try:
        within_output_dir = os.path.commonpath([str(output_dir), str(pdf_path)]) == str(output_dir)
    except ValueError:
        within_output_dir = False

    if not within_output_dir:
        raise InvalidRequestError("Invalid summary id")

    if not pdf_path.is_file():
        raise NotFoundError("PDF not found.")

    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path.name)

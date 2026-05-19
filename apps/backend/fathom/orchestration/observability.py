from __future__ import annotations

import logging
import time
from typing import Any

from fathom.core.errors import AppError
from fathom.services.downloader import DownloadError
from fathom.services.summarizer import SummarizationError
from fathom.services.transcriber import TranscriptionError


def elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


def log_stage(
    logger: logging.Logger,
    label: str,
    *,
    job_start: float,
    stage: str,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    logger.log(level, label, extra={"elapsed_ms": elapsed_ms(job_start), "stage": stage, **fields})


def log_step(
    logger: logging.Logger,
    label: str,
    *,
    duration_ms: float,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    logger.log(level, label, extra={"duration_ms": round(duration_ms, 2), **fields})


def extract_job_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, DownloadError):
        return "source_download_failed", exc.detail
    if isinstance(exc, TranscriptionError):
        return "transcription_failed", exc.detail
    if isinstance(exc, SummarizationError):
        return "summary_failed", exc.detail
    if isinstance(exc, AppError):
        return exc.code, exc.detail
    return "internal_error", "Unexpected worker error."

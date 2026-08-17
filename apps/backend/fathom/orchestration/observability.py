from __future__ import annotations

import logging
import time
from typing import Any

from fathom.core.errors import AppError
from fathom.services.downloader import AudioTooLargeError, DownloadError
from fathom.services.provider_resilience import ProviderFailureKind, ProviderOperationError
from fathom.services.summarizer import SummarizationError
from fathom.services.transcriber import TranscriptionError

PROVIDER_TEMPORARILY_UNAVAILABLE_MESSAGE = (
    "A service Talven relies on is temporarily unavailable. Your source is fine. Please try again in a few minutes."
)
PROVIDER_CAPACITY_REACHED_MESSAGE = (
    "Talven is handling unusually high demand. Your source is fine. Please try again in a few minutes."
)


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
    if isinstance(exc, ProviderOperationError) and exc.kind == ProviderFailureKind.RATE_LIMIT:
        return "provider_capacity_reached", PROVIDER_CAPACITY_REACHED_MESSAGE
    if isinstance(exc, ProviderOperationError) and exc.kind == ProviderFailureKind.TRANSIENT:
        return "provider_temporarily_unavailable", PROVIDER_TEMPORARILY_UNAVAILABLE_MESSAGE
    if isinstance(exc, AudioTooLargeError):
        return "source_audio_too_large", "This video's audio is larger than Talven's 100 MB limit."
    if isinstance(exc, DownloadError):
        return "source_download_failed", exc.detail
    if isinstance(exc, TranscriptionError):
        return "transcription_failed", exc.detail
    if isinstance(exc, SummarizationError):
        return "summary_failed", exc.detail
    if isinstance(exc, AppError):
        return exc.code, exc.detail
    return "internal_error", "Unexpected worker error."

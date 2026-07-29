from __future__ import annotations

import asyncio
from typing import Any

from groq import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    Groq,
    RateLimitError,
)

from fathom.core.config import DEFAULT_PROVIDER_TRANSCRIPTION_DEADLINE_SECONDS
from fathom.services.provider_resilience import (
    CallableProviderAdapter,
    ProviderFailureKind,
    ProviderOperationError,
    RetryPolicy,
    call_with_resilience,
    extract_retry_after_seconds,
    retryable_status,
)


class TranscriptionError(ProviderOperationError):
    def __init__(
        self,
        detail: str,
        *,
        kind: ProviderFailureKind = ProviderFailureKind.PERMANENT,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(
            detail,
            provider="groq",
            stage="transcribing",
            kind=kind,
            retry_after_seconds=retry_after_seconds,
        )


def _extract_groq_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if not isinstance(text, str):
        raise TranscriptionError(
            "Groq response missing text.",
            kind=ProviderFailureKind.TRANSIENT,
        )
    if not text.strip():
        raise TranscriptionError(
            "Empty transcript.",
            kind=ProviderFailureKind.TRANSIENT,
        )
    return text


def transcribe_url(
    media_url: str,
    api_key: str,
    model: str,
    *,
    timeout_seconds: float = 60.0,
) -> str:
    if not api_key:
        raise TranscriptionError("Missing GROQ_API_KEY.")

    with Groq(
        api_key=api_key,
        max_retries=0,
        timeout=timeout_seconds,
    ) as client:
        response = client.audio.transcriptions.create(
            url=media_url,
            model=model,
            response_format="json",
            temperature=0.0,
        )
    return _extract_groq_text(response)


async def transcribe_url_with_resilience(
    media_url: str,
    api_key: str,
    model: str,
    *,
    deadline_seconds: float = DEFAULT_PROVIDER_TRANSCRIPTION_DEADLINE_SECONDS,
) -> str:
    request_timeout_seconds = min(deadline_seconds, 60.0)

    async def operation() -> str:
        return await asyncio.to_thread(
            transcribe_url,
            media_url,
            api_key,
            model,
            timeout_seconds=request_timeout_seconds,
        )

    adapter = CallableProviderAdapter(
        provider="groq",
        stage="transcribing",
        operation=operation,
        error_classifier=_classify_groq_error,
        deadline_error_factory=_transcription_deadline_error,
    )
    return await call_with_resilience(
        adapter,
        RetryPolicy(deadline_seconds=deadline_seconds),
    )


def _classify_groq_error(exc: Exception) -> TranscriptionError:
    retry_after_seconds = extract_retry_after_seconds(exc)
    if isinstance(exc, RateLimitError):
        return TranscriptionError(
            "Groq rate limit reached.",
            kind=ProviderFailureKind.RATE_LIMIT,
            retry_after_seconds=retry_after_seconds,
        )
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return TranscriptionError(
            "Groq is temporarily unavailable.",
            kind=ProviderFailureKind.TRANSIENT,
        )
    if isinstance(exc, APIStatusError):
        status_code = getattr(exc, "status_code", None)
        if retryable_status(status_code):
            return TranscriptionError(
                "Groq is temporarily unavailable.",
                kind=ProviderFailureKind.TRANSIENT,
                retry_after_seconds=retry_after_seconds,
            )
        return TranscriptionError("Groq rejected the transcription request.")
    if isinstance(exc, APIError):
        return TranscriptionError(
            "Groq returned an invalid response.",
            kind=ProviderFailureKind.TRANSIENT,
        )
    return TranscriptionError("Groq transcription request failed.")


def _transcription_deadline_error() -> TranscriptionError:
    return TranscriptionError(
        "Groq transcription deadline exceeded.",
        kind=ProviderFailureKind.TRANSIENT,
    )

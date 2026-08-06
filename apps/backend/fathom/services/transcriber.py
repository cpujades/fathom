from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, cast

from groq import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncGroq,
    RateLimitError,
)

from fathom.schemas.transcripts import TranscriptionResult, TranscriptSegment
from fathom.services.provider_resilience import (
    CallableProviderAdapter,
    ProviderFailureKind,
    ProviderOperationError,
    RetryPolicy,
    call_with_resilience,
    extract_retry_after_seconds,
    retryable_status,
)

GROQ_TRANSCRIPTION_TIMEOUT_SECONDS = 120.0


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


def _extract_groq_transcription(response: Any) -> TranscriptionResult:
    text = getattr(response, "text", None)
    if not isinstance(text, str):
        raise TranscriptionError(
            "Groq response missing text.",
            kind=ProviderFailureKind.INVALID_RESPONSE,
        )
    if not text.strip():
        raise TranscriptionError(
            "Empty transcript.",
            kind=ProviderFailureKind.INVALID_RESPONSE,
        )

    raw_segments = getattr(response, "segments", None)
    if raw_segments is None:
        raise TranscriptionError(
            "Groq response missing timestamp segments.",
            kind=ProviderFailureKind.INVALID_RESPONSE,
        )
    if not isinstance(raw_segments, list):
        raise TranscriptionError(
            "Groq response contained invalid timestamp segments.",
            kind=ProviderFailureKind.INVALID_RESPONSE,
        )

    segments: list[TranscriptSegment] = []
    previous_start = 0.0
    for raw_segment in raw_segments:
        raw_start = _segment_value(raw_segment, "start")
        raw_end = _segment_value(raw_segment, "end")
        raw_text = _segment_value(raw_segment, "text")
        if (
            not isinstance(raw_start, (int, float))
            or isinstance(raw_start, bool)
            or not isinstance(raw_end, (int, float))
            or isinstance(raw_end, bool)
            or not isinstance(raw_text, str)
        ):
            raise TranscriptionError(
                "Groq response contained invalid timestamp segments.",
                kind=ProviderFailureKind.INVALID_RESPONSE,
            )

        segment_text = raw_text.strip()
        if not segment_text:
            continue
        try:
            segment = TranscriptSegment(
                segment_index=len(segments),
                start_seconds=float(raw_start),
                end_seconds=float(raw_end),
                text=segment_text,
            )
        except ValueError as exc:
            raise TranscriptionError(
                "Groq response contained invalid timestamp segments.",
                kind=ProviderFailureKind.INVALID_RESPONSE,
            ) from exc
        if segments and segment.start_seconds < previous_start:
            raise TranscriptionError(
                "Groq response timestamp segments were out of order.",
                kind=ProviderFailureKind.INVALID_RESPONSE,
            )
        segments.append(segment)
        previous_start = segment.start_seconds

    if not segments:
        raise TranscriptionError(
            "Groq response contained no timestamp segments.",
            kind=ProviderFailureKind.INVALID_RESPONSE,
        )
    return TranscriptionResult(text=text, segments=tuple(segments))


def _segment_value(segment: object, name: str) -> object:
    if isinstance(segment, Mapping):
        return cast(Mapping[str, object], segment).get(name)
    return getattr(segment, name, None)


async def transcribe_url(
    media_url: str,
    api_key: str,
    model: str,
    *,
    timeout_seconds: float = GROQ_TRANSCRIPTION_TIMEOUT_SECONDS,
) -> TranscriptionResult:
    if not api_key:
        raise TranscriptionError("Missing GROQ_API_KEY.")

    timestamp_granularities: list[Literal["word", "segment"]] = ["segment"]
    async with AsyncGroq(
        api_key=api_key,
        max_retries=0,
        timeout=timeout_seconds,
    ) as client:
        response = await client.audio.transcriptions.create(
            url=media_url,
            model=model,
            response_format="verbose_json",
            temperature=0.0,
            timestamp_granularities=timestamp_granularities,
        )
    return _extract_groq_transcription(response)


async def transcribe_url_with_resilience(
    media_url: str,
    api_key: str,
    model: str,
    *,
    timeout_seconds: float = GROQ_TRANSCRIPTION_TIMEOUT_SECONDS,
) -> TranscriptionResult:
    async def operation() -> TranscriptionResult:
        return await transcribe_url(
            media_url,
            api_key,
            model,
            timeout_seconds=timeout_seconds,
        )

    adapter = CallableProviderAdapter(
        provider="groq",
        stage="transcribing",
        operation=operation,
        error_classifier=_classify_groq_error,
        timeout_error_factory=_transcription_timeout_error,
    )
    return await call_with_resilience(
        adapter,
        RetryPolicy(attempt_timeout_seconds=timeout_seconds),
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
            kind=ProviderFailureKind.INVALID_RESPONSE,
        )
    return TranscriptionError("Groq transcription request failed.")


def _transcription_timeout_error() -> TranscriptionError:
    return TranscriptionError(
        "Groq transcription request timed out.",
        kind=ProviderFailureKind.TRANSIENT,
    )

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from fathom.core.config import DEFAULT_PROVIDER_SUMMARY_DEADLINE_SECONDS
from fathom.core.constants import SYSTEM_PROMPT
from fathom.services.provider_resilience import (
    CallableProviderAdapter,
    ProviderFailureKind,
    ProviderOperationError,
    RetryPolicy,
    call_with_resilience,
    extract_retry_after_seconds,
    retryable_status,
)

# Default OpenRouter model for summarization
OPENROUTER_MODEL = "x-ai/grok-4.3"

# OpenRouter metadata headers (optional but recommended)
OPENROUTER_APP_NAME = "fathom"


class SummarizationError(ProviderOperationError):
    def __init__(
        self,
        detail: str,
        *,
        kind: ProviderFailureKind = ProviderFailureKind.PERMANENT,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(
            detail,
            provider="openrouter",
            stage="summarizing",
            kind=kind,
            retry_after_seconds=retry_after_seconds,
        )


async def summarize_transcript(
    transcript: str,
    api_key: str,
    *,
    deadline_seconds: float = DEFAULT_PROVIDER_SUMMARY_DEADLINE_SECONDS,
) -> str:
    if not api_key:
        raise SummarizationError("Missing OPENROUTER_API_KEY.")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        max_retries=0,
        timeout=600,
        default_headers={
            "X-Title": OPENROUTER_APP_NAME,
        },
    )

    async def operation() -> str:
        response = await client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
            temperature=0.2,
        )

        content: Any = response.choices[0].message.content if response.choices else None
        if not isinstance(content, str) or not content.strip():
            raise SummarizationError(
                "Empty summary response.",
                kind=ProviderFailureKind.TRANSIENT,
            )
        return content.strip()

    adapter = CallableProviderAdapter(
        provider="openrouter",
        stage="summarizing",
        operation=operation,
        error_classifier=_classify_openrouter_error,
        deadline_error_factory=_summary_deadline_error,
    )
    async with client:
        return await call_with_resilience(
            adapter,
            RetryPolicy(deadline_seconds=deadline_seconds),
        )


async def stream_summarize_transcript(
    transcript: str,
    api_key: str,
    *,
    deadline_seconds: float = DEFAULT_PROVIDER_SUMMARY_DEADLINE_SECONDS,
) -> AsyncIterator[str]:
    if not api_key:
        raise SummarizationError("Missing OPENROUTER_API_KEY.")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        max_retries=0,
        timeout=600,
        default_headers={
            "X-Title": OPENROUTER_APP_NAME,
        },
    )

    async def open_stream() -> Any:
        return await client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
            temperature=0,
            stream=True,
        )

    adapter = CallableProviderAdapter(
        provider="openrouter",
        stage="summarizing",
        operation=open_stream,
        error_classifier=_classify_openrouter_error,
        deadline_error_factory=_summary_deadline_error,
    )
    try:
        async with client, asyncio.timeout(deadline_seconds):
            stream = await call_with_resilience(
                adapter,
                RetryPolicy(deadline_seconds=deadline_seconds),
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = getattr(chunk.choices[0].delta, "content", None)
                if isinstance(delta, str) and delta:
                    yield delta
    except asyncio.CancelledError:
        raise
    except TimeoutError as exc:
        raise _summary_deadline_error() from exc
    except ProviderOperationError:
        raise
    except Exception as exc:
        raise _classify_openrouter_error(exc) from exc


def _classify_openrouter_error(exc: Exception) -> SummarizationError:
    retry_after_seconds = extract_retry_after_seconds(exc)
    if isinstance(exc, RateLimitError):
        return SummarizationError(
            "OpenRouter rate limit reached.",
            kind=ProviderFailureKind.RATE_LIMIT,
            retry_after_seconds=retry_after_seconds,
        )
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return SummarizationError(
            "OpenRouter is temporarily unavailable.",
            kind=ProviderFailureKind.TRANSIENT,
        )
    if isinstance(exc, APIStatusError):
        status_code = getattr(exc, "status_code", None)
        if retryable_status(status_code):
            return SummarizationError(
                "OpenRouter is temporarily unavailable.",
                kind=ProviderFailureKind.TRANSIENT,
                retry_after_seconds=retry_after_seconds,
            )
        return SummarizationError("OpenRouter rejected the summary request.")
    if isinstance(exc, APIError):
        return SummarizationError(
            "OpenRouter returned an invalid response.",
            kind=ProviderFailureKind.TRANSIENT,
        )
    return SummarizationError("OpenRouter summary request failed.")


def _summary_deadline_error() -> SummarizationError:
    return SummarizationError(
        "OpenRouter summary deadline exceeded.",
        kind=ProviderFailureKind.TRANSIENT,
    )

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Generic, Protocol, TypeVar

from fathom.core.errors import ExternalServiceError

DEFAULT_PROVIDER_MAX_ATTEMPTS = 3
DEFAULT_PROVIDER_BACKOFF_BASE_SECONDS = 0.5
DEFAULT_PROVIDER_BACKOFF_MAX_SECONDS = 8.0
DEFAULT_PROVIDER_RETRY_AFTER_MAX_SECONDS = 60.0
DEFAULT_PROVIDER_JITTER_RATIO = 0.25

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)


class ProviderFailureKind(StrEnum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    RATE_LIMIT = "rate_limit"
    CANCELLED = "cancelled"


class ProviderOperationError(ExternalServiceError):
    """Safe provider failure with explicit retry semantics."""

    def __init__(
        self,
        detail: str,
        *,
        provider: str,
        stage: str,
        kind: ProviderFailureKind,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(detail)
        self.provider = provider
        self.stage = stage
        self.kind = kind
        self.retry_after_seconds = retry_after_seconds

    @property
    def retryable(self) -> bool:
        return self.kind in {
            ProviderFailureKind.TRANSIENT,
            ProviderFailureKind.RATE_LIMIT,
        }


@dataclass(frozen=True)
class RetryPolicy:
    deadline_seconds: float
    max_attempts: int = DEFAULT_PROVIDER_MAX_ATTEMPTS
    backoff_base_seconds: float = DEFAULT_PROVIDER_BACKOFF_BASE_SECONDS
    backoff_max_seconds: float = DEFAULT_PROVIDER_BACKOFF_MAX_SECONDS
    retry_after_max_seconds: float = DEFAULT_PROVIDER_RETRY_AFTER_MAX_SECONDS
    jitter_ratio: float = DEFAULT_PROVIDER_JITTER_RATIO

    def __post_init__(self) -> None:
        if self.deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be greater than zero")
        if not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if self.backoff_base_seconds < 0:
            raise ValueError("backoff_base_seconds cannot be negative")
        if self.backoff_max_seconds < self.backoff_base_seconds:
            raise ValueError("backoff_max_seconds cannot be less than the base delay")
        if self.retry_after_max_seconds < 0:
            raise ValueError("retry_after_max_seconds cannot be negative")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between zero and one")


class AsyncProviderAdapter(Protocol[T_co]):
    @property
    def provider(self) -> str: ...

    @property
    def stage(self) -> str: ...

    async def invoke(self) -> T_co: ...

    def classify_error(self, exc: Exception) -> ProviderOperationError: ...

    def deadline_error(self) -> ProviderOperationError: ...


@dataclass(frozen=True)
class CallableProviderAdapter(Generic[T]):
    provider: str
    stage: str
    operation: Callable[[], Awaitable[T]]
    error_classifier: Callable[[Exception], ProviderOperationError]
    deadline_error_factory: Callable[[], ProviderOperationError]

    async def invoke(self) -> T:
        return await self.operation()

    def classify_error(self, exc: Exception) -> ProviderOperationError:
        return self.error_classifier(exc)

    def deadline_error(self) -> ProviderOperationError:
        return self.deadline_error_factory()


async def call_with_resilience(
    adapter: AsyncProviderAdapter[T],
    policy: RetryPolicy,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    random_source: Callable[[], float] = random.random,
    monotonic: Callable[[], float] = time.monotonic,
) -> T:
    """Run one provider operation within a total deadline and bounded retry budget."""
    deadline_at = monotonic() + policy.deadline_seconds
    last_error: ProviderOperationError | None = None

    for attempt in range(1, policy.max_attempts + 1):
        remaining_seconds = deadline_at - monotonic()
        if remaining_seconds <= 0:
            raise adapter.deadline_error() from last_error

        try:
            async with asyncio.timeout(remaining_seconds):
                return await adapter.invoke()
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            raise adapter.deadline_error() from exc
        except ProviderOperationError as exc:
            provider_error = exc
        except Exception as exc:
            provider_error = adapter.classify_error(exc)

        last_error = provider_error
        if not provider_error.retryable or attempt >= policy.max_attempts:
            raise provider_error

        delay_seconds = compute_retry_delay(
            policy,
            attempt=attempt,
            retry_after_seconds=provider_error.retry_after_seconds,
            random_value=random_source(),
        )
        remaining_seconds = deadline_at - monotonic()
        if delay_seconds >= remaining_seconds:
            raise adapter.deadline_error() from provider_error
        await sleep(delay_seconds)

    raise adapter.deadline_error() from last_error


def compute_retry_delay(
    policy: RetryPolicy,
    *,
    attempt: int,
    retry_after_seconds: float | None = None,
    random_value: float | None = None,
) -> float:
    if retry_after_seconds is not None and retry_after_seconds > 0:
        return min(retry_after_seconds, policy.retry_after_max_seconds)

    bounded_attempt = max(attempt - 1, 0)
    exponential_delay = min(
        policy.backoff_base_seconds * (2**bounded_attempt),
        policy.backoff_max_seconds,
    )
    jitter_sample = random.random() if random_value is None else min(max(random_value, 0.0), 1.0)
    jitter_multiplier = 1 - (policy.jitter_ratio * jitter_sample)
    return max(exponential_delay * jitter_multiplier, 0.0)


def extract_retry_after_seconds(
    exc: Exception,
    *,
    now: datetime | None = None,
) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not isinstance(headers, Mapping):
        return None

    retry_after_ms = _header_value(headers, "retry-after-ms")
    if retry_after_ms:
        try:
            milliseconds = float(retry_after_ms)
        except ValueError:
            pass
        else:
            return milliseconds / 1000 if milliseconds > 0 else None

    retry_after = _header_value(headers, "retry-after")
    if not retry_after:
        return None
    try:
        seconds = float(retry_after)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(retry_after)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        current_time = now or datetime.now(UTC)
        seconds = (retry_at - current_time).total_seconds()

    return seconds if seconds > 0 else None


def classify_failure_kind(exc: BaseException) -> ProviderFailureKind:
    if isinstance(exc, asyncio.CancelledError):
        return ProviderFailureKind.CANCELLED
    if isinstance(exc, ProviderOperationError):
        return exc.kind
    return ProviderFailureKind.PERMANENT


def retryable_status(status_code: int | None) -> bool:
    return status_code in {408, 409, 429} or bool(status_code and status_code >= 500)


def _header_value(headers: Mapping[object, object], name: str) -> str | None:
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == name and isinstance(value, str):
            return value.strip()
    return None

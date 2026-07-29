from __future__ import annotations

import asyncio
import unittest
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from groq import APIConnectionError as GroqConnectionError
from groq import APIStatusError as GroqStatusError
from groq import RateLimitError as GroqRateLimitError
from openai import APIConnectionError as OpenAIConnectionError
from openai import APIStatusError as OpenAIStatusError
from openai import RateLimitError as OpenAIRateLimitError
from pydantic import ValidationError

from fathom.core.config import (
    DEFAULT_PROVIDER_SUMMARY_DEADLINE_SECONDS,
    DEFAULT_PROVIDER_TRANSCRIPTION_DEADLINE_SECONDS,
    Settings,
)
from fathom.orchestration.runner import _handle_claimed_job
from fathom.services.provider_resilience import (
    CallableProviderAdapter,
    ProviderFailureKind,
    ProviderOperationError,
    RetryPolicy,
    call_with_resilience,
    classify_failure_kind,
    compute_retry_delay,
    extract_retry_after_seconds,
    retryable_status,
)
from fathom.services.summarizer import _classify_openrouter_error
from fathom.services.transcriber import _classify_groq_error, transcribe_url
from supabase import AsyncClient


class FakeProviderError(ProviderOperationError):
    def __init__(
        self,
        *,
        kind: ProviderFailureKind,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(
            "Provider request failed.",
            provider="fake",
            stage="testing",
            kind=kind,
            retry_after_seconds=retry_after_seconds,
        )


def _fake_adapter(
    operation: Callable[[], Awaitable[str]],
) -> CallableProviderAdapter[str]:
    return CallableProviderAdapter(
        provider="fake",
        stage="testing",
        operation=operation,
        error_classifier=lambda exc: FakeProviderError(kind=ProviderFailureKind.PERMANENT),
        deadline_error_factory=lambda: FakeProviderError(kind=ProviderFailureKind.TRANSIENT),
    )


class ProviderResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_failures_retry_with_bounded_backoff_then_succeed(self) -> None:
        attempts = 0
        delays: list[float] = []

        async def operation() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise FakeProviderError(kind=ProviderFailureKind.TRANSIENT)
            return "ok"

        async def record_sleep(delay_seconds: float) -> None:
            delays.append(delay_seconds)

        result = await call_with_resilience(
            _fake_adapter(operation),
            RetryPolicy(deadline_seconds=30),
            sleep=record_sleep,
            random_source=lambda: 0.0,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(attempts, 3)
        self.assertEqual(delays, [0.5, 1.0])

    async def test_permanent_failure_is_not_retried(self) -> None:
        operation = AsyncMock(side_effect=FakeProviderError(kind=ProviderFailureKind.PERMANENT))

        with self.assertRaises(FakeProviderError) as raised:
            await call_with_resilience(
                _fake_adapter(operation),
                RetryPolicy(deadline_seconds=30),
            )

        self.assertEqual(raised.exception.kind, ProviderFailureKind.PERMANENT)
        operation.assert_awaited_once()

    async def test_rate_limit_honors_capped_retry_after(self) -> None:
        attempts = 0
        delays: list[float] = []

        async def operation() -> str:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise FakeProviderError(
                    kind=ProviderFailureKind.RATE_LIMIT,
                    retry_after_seconds=120,
                )
            return "ok"

        async def record_sleep(delay_seconds: float) -> None:
            delays.append(delay_seconds)

        result = await call_with_resilience(
            _fake_adapter(operation),
            RetryPolicy(deadline_seconds=180),
            sleep=record_sleep,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(delays, [60])

    async def test_retry_budget_is_bounded(self) -> None:
        operation = AsyncMock(side_effect=FakeProviderError(kind=ProviderFailureKind.TRANSIENT))

        with self.assertRaises(FakeProviderError):
            await call_with_resilience(
                _fake_adapter(operation),
                RetryPolicy(deadline_seconds=30),
                sleep=AsyncMock(),
            )

        self.assertEqual(operation.await_count, 3)

    async def test_deadline_expires_without_additional_attempt(self) -> None:
        operation = AsyncMock(side_effect=FakeProviderError(kind=ProviderFailureKind.TRANSIENT))
        monotonic_values = iter([0.0, 0.0, 0.0, 0.4])

        with self.assertRaises(FakeProviderError) as raised:
            await call_with_resilience(
                _fake_adapter(operation),
                RetryPolicy(
                    deadline_seconds=0.25,
                    backoff_base_seconds=0.5,
                    backoff_max_seconds=0.5,
                ),
                monotonic=lambda: next(monotonic_values),
            )

        self.assertEqual(raised.exception.kind, ProviderFailureKind.TRANSIENT)
        operation.assert_awaited_once()

    async def test_cancellation_propagates_without_retry(self) -> None:
        operation = AsyncMock(side_effect=asyncio.CancelledError)

        with self.assertRaises(asyncio.CancelledError):
            await call_with_resilience(
                _fake_adapter(operation),
                RetryPolicy(deadline_seconds=30),
            )

        operation.assert_awaited_once()
        self.assertEqual(
            classify_failure_kind(asyncio.CancelledError()),
            ProviderFailureKind.CANCELLED,
        )

    def test_retry_policy_rejects_invalid_limits(self) -> None:
        with self.assertRaises(ValueError):
            RetryPolicy(deadline_seconds=0)
        with self.assertRaises(ValueError):
            RetryPolicy(deadline_seconds=1, max_attempts=0)
        with self.assertRaises(ValueError):
            RetryPolicy(deadline_seconds=1, backoff_base_seconds=2, backoff_max_seconds=1)
        with self.assertRaises(ValueError):
            RetryPolicy(deadline_seconds=1, jitter_ratio=1.1)

    def test_backoff_jitter_and_retry_after_are_bounded(self) -> None:
        policy = RetryPolicy(
            deadline_seconds=30,
            backoff_base_seconds=2,
            backoff_max_seconds=4,
            retry_after_max_seconds=10,
            jitter_ratio=0.25,
        )
        self.assertEqual(compute_retry_delay(policy, attempt=3, random_value=0), 4)
        self.assertEqual(compute_retry_delay(policy, attempt=3, random_value=1), 3)
        self.assertEqual(
            compute_retry_delay(policy, attempt=1, retry_after_seconds=30),
            10,
        )

    def test_retry_after_parses_seconds_milliseconds_and_http_date(self) -> None:
        now = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
        seconds_error = RuntimeError()
        seconds_error.response = SimpleNamespace(headers={"Retry-After": "12"})  # type: ignore[attr-defined]
        milliseconds_error = RuntimeError()
        milliseconds_error.response = SimpleNamespace(  # type: ignore[attr-defined]
            headers={"retry-after-ms": "1250"}
        )
        date_error = RuntimeError()
        date_error.response = SimpleNamespace(  # type: ignore[attr-defined]
            headers={"retry-after": (now + timedelta(seconds=30)).strftime("%a, %d %b %Y %H:%M:%S GMT")}
        )

        self.assertEqual(extract_retry_after_seconds(seconds_error, now=now), 12)
        self.assertEqual(extract_retry_after_seconds(milliseconds_error, now=now), 1.25)
        self.assertEqual(extract_retry_after_seconds(date_error, now=now), 30)

    def test_retryable_statuses_are_explicit(self) -> None:
        for status_code in (408, 409, 429, 500, 503):
            self.assertTrue(retryable_status(status_code))
        for status_code in (None, 400, 401, 403, 404, 422, 425):
            self.assertFalse(retryable_status(status_code))

    def test_openrouter_errors_are_classified_by_retry_semantics(self) -> None:
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        connection_error = OpenAIConnectionError(request=request)
        rate_limit_response = httpx.Response(
            429,
            headers={"Retry-After": "7"},
            request=request,
        )
        bad_request_response = httpx.Response(400, request=request)

        self.assertEqual(
            _classify_openrouter_error(connection_error).kind,
            ProviderFailureKind.TRANSIENT,
        )
        rate_limit = _classify_openrouter_error(
            OpenAIRateLimitError("limited", response=rate_limit_response, body=None)
        )
        self.assertEqual(rate_limit.kind, ProviderFailureKind.RATE_LIMIT)
        self.assertEqual(rate_limit.retry_after_seconds, 7)
        self.assertEqual(
            _classify_openrouter_error(OpenAIStatusError("bad request", response=bad_request_response, body=None)).kind,
            ProviderFailureKind.PERMANENT,
        )

    def test_groq_errors_are_classified_by_retry_semantics(self) -> None:
        request = httpx.Request("POST", "https://api.groq.com/openai/v1/audio/transcriptions")
        connection_error = GroqConnectionError(request=request)
        rate_limit_response = httpx.Response(
            429,
            headers={"retry-after-ms": "2500"},
            request=request,
        )
        server_error_response = httpx.Response(503, request=request)

        self.assertEqual(
            _classify_groq_error(connection_error).kind,
            ProviderFailureKind.TRANSIENT,
        )
        rate_limit = _classify_groq_error(GroqRateLimitError("limited", response=rate_limit_response, body=None))
        self.assertEqual(rate_limit.kind, ProviderFailureKind.RATE_LIMIT)
        self.assertEqual(rate_limit.retry_after_seconds, 2.5)
        self.assertEqual(
            _classify_groq_error(GroqStatusError("unavailable", response=server_error_response, body=None)).kind,
            ProviderFailureKind.TRANSIENT,
        )

    async def test_groq_transcription_uses_cancellable_async_client(self) -> None:
        create = AsyncMock(return_value=SimpleNamespace(text="transcript"))
        client = SimpleNamespace(
            audio=SimpleNamespace(
                transcriptions=SimpleNamespace(create=create),
            )
        )
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "fathom.services.transcriber.AsyncGroq",
            return_value=context,
        ) as client_factory:
            result = await transcribe_url(
                "https://storage.example/audio.webm",
                "groq-key",
                "whisper",
                timeout_seconds=15,
            )

        self.assertEqual(result, "transcript")
        client_factory.assert_called_once_with(
            api_key="groq-key",
            max_retries=0,
            timeout=15,
        )
        create.assert_awaited_once_with(
            url="https://storage.example/audio.webm",
            model="whisper",
            response_format="json",
            temperature=0.0,
        )


class ProviderDeadlineSettingsTests(unittest.TestCase):
    def _settings_values(self) -> dict[str, str]:
        return {
            "OPENROUTER_API_KEY": "openrouter",
            "GROQ_API_KEY": "groq",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "publishable",
            "SUPABASE_SECRET_KEY": "secret",
        }

    def test_provider_deadline_defaults_preserve_existing_retry_envelopes(self) -> None:
        settings = Settings.model_validate(self._settings_values())

        self.assertEqual(
            settings.provider_transcription_deadline_seconds,
            DEFAULT_PROVIDER_TRANSCRIPTION_DEADLINE_SECONDS,
        )
        self.assertEqual(
            settings.provider_summary_deadline_seconds,
            DEFAULT_PROVIDER_SUMMARY_DEADLINE_SECONDS,
        )

    def test_provider_deadlines_must_be_positive_and_bounded(self) -> None:
        values = self._settings_values()
        values["PROVIDER_TRANSCRIPTION_DEADLINE_SECONDS"] = "0"
        with self.assertRaises(ValidationError):
            Settings.model_validate(values)

        values = self._settings_values()
        values["PROVIDER_SUMMARY_DEADLINE_SECONDS"] = "3601"
        with self.assertRaises(ValidationError):
            Settings.model_validate(values)


class ProviderWorkerRetryTests(unittest.IsolatedAsyncioTestCase):
    def _job(self) -> dict[str, object]:
        return {
            "id": "11111111-1111-1111-1111-111111111111",
            "url": "https://www.youtube.com/watch?v=provider",
            "user_id": "22222222-2222-2222-2222-222222222222",
            "attempt_count": 1,
            "lease_token": "33333333-3333-3333-3333-333333333333",
        }

    async def test_permanent_provider_failure_is_not_requeued(self) -> None:
        settings = cast(Settings, SimpleNamespace())
        admin_client = cast(AsyncClient, object())
        error = FakeProviderError(kind=ProviderFailureKind.PERMANENT)

        with (
            patch(
                "fathom.orchestration.runner._run_job_with_heartbeat",
                AsyncMock(side_effect=error),
            ),
            patch("fathom.orchestration.runner.record_job_event_best_effort", AsyncMock()),
            patch("fathom.orchestration.runner.mark_job_retry", AsyncMock()) as retry,
            patch("fathom.orchestration.runner.mark_job_failed", AsyncMock()) as failed,
        ):
            await _handle_claimed_job(self._job(), settings, admin_client)

        retry.assert_not_awaited()
        failed.assert_awaited_once()

    async def test_rate_limit_requeues_using_retry_after(self) -> None:
        settings = cast(Settings, SimpleNamespace())
        admin_client = cast(AsyncClient, object())
        error = FakeProviderError(
            kind=ProviderFailureKind.RATE_LIMIT,
            retry_after_seconds=45,
        )

        with (
            patch(
                "fathom.orchestration.runner._run_job_with_heartbeat",
                AsyncMock(side_effect=error),
            ),
            patch("fathom.orchestration.runner.record_job_event_best_effort", AsyncMock()),
            patch("fathom.orchestration.runner.mark_job_retry", AsyncMock()) as retry,
            patch("fathom.orchestration.runner.mark_job_failed", AsyncMock()),
            patch("fathom.orchestration.runner.datetime") as current_datetime,
        ):
            now = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
            current_datetime.now.return_value = now
            await _handle_claimed_job(self._job(), settings, admin_client)

        retry.assert_awaited_once()
        self.assertEqual(
            retry.await_args.kwargs["run_after"],
            now + timedelta(seconds=45),
        )


if __name__ == "__main__":
    unittest.main()

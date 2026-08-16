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

from fathom.core.config import Settings
from fathom.core.constants import GROQ_SIGNED_URL_TTL_SECONDS
from fathom.orchestration.observability import extract_job_error
from fathom.orchestration.runner import _handle_claimed_job
from fathom.services.downloader import AudioTooLargeError
from fathom.services.provider_resilience import (
    PROVIDER_MAX_ATTEMPTS,
    BackoffPolicy,
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
from fathom.services.summarizer import (
    OPENROUTER_SUMMARY_TIMEOUT_SECONDS,
    SummarizationError,
    _classify_openrouter_error,
)
from fathom.services.transcriber import (
    GROQ_TRANSCRIPTION_TIMEOUT_SECONDS,
    TranscriptionError,
    _classify_groq_error,
    transcribe_url,
)
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
        timeout_error_factory=lambda: FakeProviderError(kind=ProviderFailureKind.TRANSIENT),
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
            RetryPolicy(attempt_timeout_seconds=30),
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
                RetryPolicy(attempt_timeout_seconds=30),
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
            RetryPolicy(attempt_timeout_seconds=180),
            sleep=record_sleep,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(delays, [60])

    async def test_retry_budget_is_bounded(self) -> None:
        operation = AsyncMock(side_effect=FakeProviderError(kind=ProviderFailureKind.TRANSIENT))

        with self.assertRaises(FakeProviderError):
            await call_with_resilience(
                _fake_adapter(operation),
                RetryPolicy(attempt_timeout_seconds=30),
                sleep=AsyncMock(),
            )

        self.assertEqual(operation.await_count, 3)

    async def test_each_timed_out_attempt_uses_the_retry_budget(self) -> None:
        attempts = 0

        async def operation() -> str:
            nonlocal attempts
            attempts += 1
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        with self.assertRaises(FakeProviderError) as raised:
            await call_with_resilience(
                _fake_adapter(operation),
                RetryPolicy(
                    attempt_timeout_seconds=0.001,
                    max_attempts=2,
                    backoff=BackoffPolicy(backoff_base_seconds=0, backoff_max_seconds=0),
                ),
            )

        self.assertEqual(raised.exception.kind, ProviderFailureKind.TRANSIENT)
        self.assertEqual(attempts, 2)

    async def test_cancellation_propagates_without_retry(self) -> None:
        operation = AsyncMock(side_effect=asyncio.CancelledError)

        with self.assertRaises(asyncio.CancelledError):
            await call_with_resilience(
                _fake_adapter(operation),
                RetryPolicy(attempt_timeout_seconds=30),
            )

        operation.assert_awaited_once()
        self.assertEqual(
            classify_failure_kind(asyncio.CancelledError()),
            ProviderFailureKind.CANCELLED,
        )

    def test_retry_policy_rejects_invalid_limits(self) -> None:
        with self.assertRaises(ValueError):
            RetryPolicy(attempt_timeout_seconds=0)
        with self.assertRaises(ValueError):
            RetryPolicy(attempt_timeout_seconds=1, max_attempts=0)
        with self.assertRaises(ValueError):
            BackoffPolicy(backoff_base_seconds=2, backoff_max_seconds=1)
        with self.assertRaises(ValueError):
            BackoffPolicy(jitter_ratio=1.1)

    def test_backoff_jitter_and_retry_after_are_bounded(self) -> None:
        policy = BackoffPolicy(
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

    def test_exhausted_capacity_is_user_safe_but_invalid_outputs_remain_stage_specific(self) -> None:
        groq_request = httpx.Request("POST", "https://api.groq.com/openai/v1/audio/transcriptions")
        groq_rate_limit = _classify_groq_error(
            GroqRateLimitError(
                "limited",
                response=httpx.Response(429, request=groq_request),
                body=None,
            )
        )
        openrouter_request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        openrouter_rate_limit = _classify_openrouter_error(
            OpenAIRateLimitError(
                "limited",
                response=httpx.Response(429, request=openrouter_request),
                body=None,
            )
        )

        for error in (groq_rate_limit, openrouter_rate_limit):
            code, message = extract_job_error(error)
            self.assertEqual(code, "provider_capacity_reached")
            self.assertIn("Your source is fine", message)
            self.assertNotIn("Groq", message)
            self.assertNotIn("OpenRouter", message)

        transient_code, transient_message = extract_job_error(FakeProviderError(kind=ProviderFailureKind.TRANSIENT))
        self.assertEqual(transient_code, "provider_temporarily_unavailable")
        self.assertIn("temporarily unavailable", transient_message)
        self.assertNotIn("high demand", transient_message)

        transcript_code, _ = extract_job_error(
            TranscriptionError("Invalid timestamp evidence.", kind=ProviderFailureKind.INVALID_RESPONSE)
        )
        summary_code, _ = extract_job_error(
            SummarizationError("Invalid briefing evidence.", kind=ProviderFailureKind.INVALID_RESPONSE)
        )
        self.assertEqual(transcript_code, "transcription_failed")
        self.assertEqual(summary_code, "summary_failed")

    async def test_groq_transcription_uses_cancellable_async_client(self) -> None:
        create = AsyncMock(
            return_value=SimpleNamespace(
                text="transcript",
                segments=[
                    {
                        "start": 0.0,
                        "end": 2.5,
                        "text": " transcript ",
                    }
                ],
            )
        )
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

        self.assertEqual(result.text, "transcript")
        self.assertEqual(len(result.segments), 1)
        self.assertEqual(result.segments[0].segment_index, 0)
        self.assertEqual(result.segments[0].start_seconds, 0)
        self.assertEqual(result.segments[0].end_seconds, 2.5)
        self.assertEqual(result.segments[0].text, "transcript")
        client_factory.assert_called_once_with(
            api_key="groq-key",
            max_retries=0,
            timeout=15,
        )
        create.assert_awaited_once_with(
            url="https://storage.example/audio.webm",
            model="whisper",
            response_format="verbose_json",
            temperature=0.0,
            timestamp_granularities=["segment"],
        )


class ProviderRuntimeConstantsTests(unittest.TestCase):
    def test_provider_retry_and_timeout_constants_are_explicit(self) -> None:
        self.assertEqual(PROVIDER_MAX_ATTEMPTS, 3)
        self.assertEqual(GROQ_TRANSCRIPTION_TIMEOUT_SECONDS, 120.0)
        self.assertEqual(OPENROUTER_SUMMARY_TIMEOUT_SECONDS, 300.0)
        self.assertEqual(GROQ_SIGNED_URL_TTL_SECONDS, 600)


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
        self.assertEqual(failed.await_args.kwargs["error_code"], "external_service_error")

    async def test_exhausted_provider_retries_do_not_requeue_the_whole_job(self) -> None:
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
            patch("fathom.orchestration.runner.mark_job_failed", AsyncMock()) as failed,
        ):
            await _handle_claimed_job(self._job(), settings, admin_client)

        retry.assert_not_awaited()
        failed.assert_awaited_once()
        self.assertEqual(failed.await_args.kwargs["error_code"], "provider_capacity_reached")
        self.assertIn("Your source is fine", failed.await_args.kwargs["error_message"])

    async def test_oversize_audio_is_user_safe_and_never_requeued(self) -> None:
        settings = cast(Settings, SimpleNamespace())
        admin_client = cast(AsyncClient, object())
        error = AudioTooLargeError("Source audio exceeds the supported 100 MB limit.")

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
        self.assertEqual(failed.await_args.kwargs["error_code"], "source_audio_too_large")
        self.assertIn("100 MB", failed.await_args.kwargs["error_message"])


if __name__ == "__main__":
    unittest.main()

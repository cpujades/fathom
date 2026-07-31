from __future__ import annotations

import asyncio
import unittest
from collections.abc import Awaitable, Callable

from fathom.services.provider_resilience import (
    CallableProviderAdapter,
    ProviderFailureKind,
    ProviderOperationError,
    RetryPolicy,
    call_with_resilience,
)

REHEARSAL_JOB_COUNT = 20
REHEARSAL_CONCURRENCY = 4


class FakeRehearsalError(ProviderOperationError):
    def __init__(self, kind: ProviderFailureKind) -> None:
        super().__init__(
            "Deterministic rehearsal failure.",
            provider="fake",
            stage="rehearsal",
            kind=kind,
        )


def _adapter(operation: Callable[[], Awaitable[str]]) -> CallableProviderAdapter[str]:
    return CallableProviderAdapter(
        provider="fake",
        stage="rehearsal",
        operation=operation,
        error_classifier=lambda _exc: FakeRehearsalError(ProviderFailureKind.PERMANENT),
        deadline_error_factory=lambda: FakeRehearsalError(ProviderFailureKind.TRANSIENT),
    )


class BoundedRecoveryRehearsalTests(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_fake_load_converges_with_expected_retry_outcomes(self) -> None:
        semaphore = asyncio.Semaphore(REHEARSAL_CONCURRENCY)
        attempts = [0] * REHEARSAL_JOB_COUNT
        active_operations = 0
        maximum_active_operations = 0

        async def run_job(job_index: int) -> str:
            async def operation() -> str:
                nonlocal active_operations, maximum_active_operations
                attempts[job_index] += 1
                active_operations += 1
                maximum_active_operations = max(maximum_active_operations, active_operations)
                try:
                    await asyncio.sleep(0)
                    if job_index % 7 == 0:
                        raise FakeRehearsalError(ProviderFailureKind.PERMANENT)
                    if job_index % 5 == 0 and attempts[job_index] == 1:
                        raise FakeRehearsalError(ProviderFailureKind.TRANSIENT)
                    return f"job-{job_index}:ok"
                finally:
                    active_operations -= 1

            async with semaphore:
                return await call_with_resilience(
                    _adapter(operation),
                    RetryPolicy(
                        deadline_seconds=5,
                        max_attempts=3,
                        backoff_base_seconds=0,
                        backoff_max_seconds=0,
                        jitter_ratio=0,
                    ),
                    sleep=lambda _delay: asyncio.sleep(0),
                    random_source=lambda: 0,
                )

        results = await asyncio.gather(
            *(run_job(job_index) for job_index in range(REHEARSAL_JOB_COUNT)),
            return_exceptions=True,
        )

        permanent_failures = [result for result in results if isinstance(result, FakeRehearsalError)]
        successes = [result for result in results if isinstance(result, str)]

        self.assertEqual(len(successes), 17)
        self.assertEqual(len(permanent_failures), 3)
        self.assertTrue(all(error.kind is ProviderFailureKind.PERMANENT for error in permanent_failures))
        self.assertEqual(attempts[0], 1)
        self.assertEqual(attempts[5], 2)
        self.assertEqual(attempts[10], 2)
        self.assertEqual(attempts[15], 2)
        self.assertGreater(maximum_active_operations, 1)
        self.assertLessEqual(maximum_active_operations, REHEARSAL_CONCURRENCY)


if __name__ == "__main__":
    unittest.main()

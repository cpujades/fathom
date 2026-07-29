from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from fathom.application.usage import record_usage_for_job
from fathom.core.config import Settings
from fathom.core.errors import UsageSettlementError
from fathom.orchestration.runner import _handle_claimed_job
from supabase import AsyncClient


class UsageSettlementApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_record_usage_delegates_to_atomic_settlement(self) -> None:
        settings = cast(Settings, SimpleNamespace(billing_debt_cap_seconds=600))
        admin_client = cast(AsyncClient, object())
        settlement = {
            "resolution_type": "settled",
            "settlement": {
                "duration_seconds": 1800,
                "subscription_seconds": 1200,
                "pack_seconds": 600,
                "debt_incurred_seconds": 0,
            },
        }

        with patch(
            "fathom.application.usage.settle_job_usage",
            AsyncMock(return_value=settlement),
        ) as settle:
            await record_usage_for_job(
                user_id="user-123",
                job_id="11111111-1111-1111-1111-111111111111",
                lease_token="33333333-3333-3333-3333-333333333333",
                duration_seconds=1800,
                settings=settings,
                admin_client=admin_client,
            )

        settle.assert_awaited_once_with(
            admin_client,
            job_id="11111111-1111-1111-1111-111111111111",
            lease_token="33333333-3333-3333-3333-333333333333",
            debt_cap_seconds=600,
        )

    async def test_zero_duration_still_creates_idempotency_record(self) -> None:
        settings = cast(Settings, SimpleNamespace(billing_debt_cap_seconds=600))
        admin_client = cast(AsyncClient, object())
        settlement = {
            "resolution_type": "settled",
            "settlement": {
                "duration_seconds": 0,
                "subscription_seconds": 0,
                "pack_seconds": 0,
                "debt_incurred_seconds": 0,
            },
        }

        with patch(
            "fathom.application.usage.settle_job_usage",
            AsyncMock(return_value=settlement),
        ) as settle:
            await record_usage_for_job(
                user_id="user-123",
                job_id="11111111-1111-1111-1111-111111111111",
                lease_token="33333333-3333-3333-3333-333333333333",
                duration_seconds=None,
                settings=settings,
                admin_client=admin_client,
            )

        settle.assert_awaited_once()

    async def test_settlement_failure_is_not_swallowed(self) -> None:
        settings = cast(Settings, SimpleNamespace(billing_debt_cap_seconds=600))
        admin_client = cast(AsyncClient, object())

        with patch(
            "fathom.application.usage.settle_job_usage",
            AsyncMock(side_effect=RuntimeError("database unavailable")),
        ):
            with self.assertRaises(UsageSettlementError):
                await record_usage_for_job(
                    user_id="user-123",
                    job_id="11111111-1111-1111-1111-111111111111",
                    lease_token="33333333-3333-3333-3333-333333333333",
                    duration_seconds=1800,
                    settings=settings,
                    admin_client=admin_client,
                )


class UsageSettlementWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_retryable_settlement_failure_preserves_finalization_state(self) -> None:
        settings = cast(Settings, SimpleNamespace())
        admin_client = cast(AsyncClient, object())
        job: dict[str, Any] = {
            "id": "11111111-1111-1111-1111-111111111111",
            "url": "https://www.youtube.com/watch?v=settlement",
            "user_id": "22222222-2222-2222-2222-222222222222",
            "attempt_count": 1,
            "lease_token": "33333333-3333-3333-3333-333333333333",
        }
        error = UsageSettlementError("Usage accounting could not be finalized; retrying shortly.")

        with (
            patch(
                "fathom.orchestration.runner._run_job_with_heartbeat",
                AsyncMock(side_effect=error),
            ),
            patch(
                "fathom.orchestration.runner.record_job_event_best_effort",
                AsyncMock(),
            ),
            patch(
                "fathom.orchestration.runner.mark_job_finalization_retry",
                AsyncMock(),
            ) as finalization_retry,
            patch("fathom.orchestration.runner.mark_job_retry", AsyncMock()) as generic_retry,
            patch("fathom.orchestration.runner.mark_job_failed", AsyncMock()),
        ):
            await _handle_claimed_job(job, settings, admin_client)

        finalization_retry.assert_awaited_once()
        call_kwargs = finalization_retry.await_args.kwargs
        self.assertEqual(call_kwargs["job_id"], job["id"])
        self.assertEqual(call_kwargs["lease_token"], job["lease_token"])
        self.assertEqual(call_kwargs["error_code"], "usage_settlement_failed")
        generic_retry.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

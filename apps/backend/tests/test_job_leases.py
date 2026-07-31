from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, call, patch

from fathom.core.config import Settings
from fathom.crud.supabase.jobs import (
    JobLeaseLostError,
    claim_next_job,
    create_or_reuse_job,
    mark_job_succeeded,
    update_job_progress,
)
from fathom.orchestration.jobs import process_job
from fathom.orchestration.runner import _run_job_with_heartbeat
from fathom.orchestration.summaries import SummaryResolution
from supabase import AsyncClient


def _claimed_job() -> dict[str, object]:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "user_id": "22222222-2222-2222-2222-222222222222",
        "lease_token": "33333333-3333-3333-3333-333333333333",
        "duration_seconds": 1800,
    }


class JobLeaseCrudTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_worker_uses_settlement_aware_claim_command(self) -> None:
        query = MagicMock()
        query.execute = AsyncMock(return_value=SimpleNamespace(data=None))
        client = MagicMock()
        client.rpc.return_value = query

        claimed = await claim_next_job(cast(AsyncClient, client), lease_seconds=120)

        self.assertIsNone(claimed)
        client.rpc.assert_called_once_with(
            "claim_next_settled_job",
            {"p_lease_for": "120 seconds"},
        )

    async def test_cached_job_creation_uses_lease_owned_command(self) -> None:
        query = MagicMock()
        query.execute = AsyncMock(
            return_value=SimpleNamespace(
                data={
                    "resolution_type": "new",
                    "job": {
                        "id": "11111111-1111-1111-1111-111111111111",
                        "status": "running",
                        "lease_token": "33333333-3333-3333-3333-333333333333",
                    },
                }
            )
        )
        client = MagicMock()
        client.rpc.return_value = query

        await create_or_reuse_job(
            cast(AsyncClient, client),
            user_id="22222222-2222-2222-2222-222222222222",
            url="https://www.youtube.com/watch?v=cached",
            source_key="youtube:cached",
            duration_seconds=1800,
            summary_id="55555555-5555-5555-5555-555555555555",
        )

        client.rpc.assert_called_once_with(
            "create_or_reuse_settled_job",
            {
                "p_user_id": "22222222-2222-2222-2222-222222222222",
                "p_url": "https://www.youtube.com/watch?v=cached",
                "p_source_key": "youtube:cached",
                "p_duration_seconds": 1800,
                "p_summary_id": "55555555-5555-5555-5555-555555555555",
                "p_cached_lease_for": "120 seconds",
            },
        )

    async def test_terminal_success_uses_settlement_guarded_command(self) -> None:
        query = MagicMock()
        query.execute = AsyncMock(return_value=SimpleNamespace(data=True))
        client = MagicMock()
        client.rpc.return_value = query

        await mark_job_succeeded(
            cast(AsyncClient, client),
            job_id="11111111-1111-1111-1111-111111111111",
            summary_id="55555555-5555-5555-5555-555555555555",
            lease_token="33333333-3333-3333-3333-333333333333",
        )

        client.rpc.assert_called_once_with(
            "complete_job_after_settlement",
            {
                "p_job_id": "11111111-1111-1111-1111-111111111111",
                "p_summary_id": "55555555-5555-5555-5555-555555555555",
                "p_lease_token": "33333333-3333-3333-3333-333333333333",
            },
        )

    async def test_terminal_success_rejects_missing_settlement_or_lost_lease(self) -> None:
        query = MagicMock()
        query.execute = AsyncMock(return_value=SimpleNamespace(data=False))
        client = MagicMock()
        client.rpc.return_value = query

        with self.assertRaises(JobLeaseLostError):
            await mark_job_succeeded(
                cast(AsyncClient, client),
                job_id="11111111-1111-1111-1111-111111111111",
                summary_id="55555555-5555-5555-5555-555555555555",
                lease_token="33333333-3333-3333-3333-333333333333",
            )

    async def test_guarded_progress_update_rejects_lost_lease(self) -> None:
        query = MagicMock()
        query.update.return_value = query
        query.eq.return_value = query
        query.execute = AsyncMock(return_value=SimpleNamespace(data=[]))
        client = MagicMock()
        client.table.return_value = query

        with self.assertRaises(JobLeaseLostError):
            await update_job_progress(
                cast(AsyncClient, client),
                job_id="11111111-1111-1111-1111-111111111111",
                lease_token="33333333-3333-3333-3333-333333333333",
                stage="summarizing",
            )

        self.assertEqual(
            query.eq.call_args_list,
            [
                call("id", "11111111-1111-1111-1111-111111111111"),
                call("status", "running"),
                call("lease_token", "33333333-3333-3333-3333-333333333333"),
            ],
        )


class JobLeaseOrchestrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_usage_attempt_precedes_guarded_terminal_success(self) -> None:
        settings = cast(Settings, SimpleNamespace())
        admin_client = cast(AsyncClient, object())
        job = _claimed_job()
        order: list[str] = []

        async def record_usage(**_: Any) -> None:
            order.append("usage")

        async def record_completed(**_: Any) -> None:
            order.append("completion_event")

        async def mark_succeeded(*_: Any, **__: Any) -> None:
            order.append("success")

        with (
            patch("fathom.orchestration.jobs.update_job_progress", AsyncMock()),
            patch(
                "fathom.orchestration.jobs.resolve_transcript",
                AsyncMock(
                    return_value=SimpleNamespace(
                        transcript_id="44444444-4444-4444-4444-444444444444",
                        transcript_text="Transcript",
                        segments=(),
                    )
                ),
            ),
            patch(
                "fathom.orchestration.jobs.resolve_summary",
                AsyncMock(
                    return_value=SummaryResolution(
                        summary_id="55555555-5555-5555-5555-555555555555",
                        markdown="Existing briefing",
                        cache_hit=True,
                    )
                ),
            ),
            patch("fathom.orchestration.jobs._record_usage", side_effect=record_usage),
            patch("fathom.orchestration.jobs._record_job_completed", side_effect=record_completed),
            patch("fathom.orchestration.jobs.mark_job_succeeded", side_effect=mark_succeeded) as success_mock,
        ):
            await process_job(job, settings, admin_client)

        self.assertEqual(order, ["usage", "completion_event", "success"])
        success_mock.assert_awaited_once_with(
            admin_client,
            job_id=job["id"],
            summary_id="55555555-5555-5555-5555-555555555555",
            lease_token=job["lease_token"],
        )

    async def test_heartbeat_remains_active_through_usage_and_terminal_transition(self) -> None:
        settings = cast(Settings, SimpleNamespace())
        admin_client = cast(AsyncClient, object())
        job = _claimed_job()
        lease_renewed = asyncio.Event()
        order: list[str] = []

        async def renew_lease(*_: Any, **__: Any) -> bool:
            lease_renewed.set()
            return True

        async def record_usage(**_: Any) -> None:
            await asyncio.wait_for(lease_renewed.wait(), timeout=1)
            order.append("usage")

        async def mark_succeeded(*_: Any, **__: Any) -> None:
            order.append("success")

        with (
            patch("fathom.orchestration.runner.WORKER_HEARTBEAT_INTERVAL_SECONDS", 0),
            patch("fathom.orchestration.runner.renew_job_lease", side_effect=renew_lease) as renew_mock,
            patch("fathom.orchestration.jobs.update_job_progress", AsyncMock()),
            patch(
                "fathom.orchestration.jobs.resolve_transcript",
                AsyncMock(
                    return_value=SimpleNamespace(
                        transcript_id="44444444-4444-4444-4444-444444444444",
                        transcript_text="Transcript",
                        segments=(),
                    )
                ),
            ),
            patch(
                "fathom.orchestration.jobs.resolve_summary",
                AsyncMock(
                    return_value=SummaryResolution(
                        summary_id="55555555-5555-5555-5555-555555555555",
                        markdown="Existing briefing",
                        cache_hit=True,
                    )
                ),
            ),
            patch("fathom.orchestration.jobs._record_usage", side_effect=record_usage),
            patch("fathom.orchestration.jobs._record_job_completed", AsyncMock()),
            patch("fathom.orchestration.jobs.mark_job_succeeded", side_effect=mark_succeeded),
        ):
            await _run_job_with_heartbeat(job, settings, admin_client)

        renew_mock.assert_awaited()
        self.assertEqual(order, ["usage", "success"])

    async def test_lost_lease_cancels_in_flight_processing(self) -> None:
        settings = cast(Settings, SimpleNamespace())
        admin_client = cast(AsyncClient, object())
        job = _claimed_job()
        processing_started = asyncio.Event()
        processing_cancelled = asyncio.Event()

        async def blocked_process(*_: Any, **__: Any) -> None:
            processing_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                processing_cancelled.set()

        async def lose_lease(*_: Any, **__: Any) -> bool:
            await processing_started.wait()
            return False

        with (
            patch("fathom.orchestration.runner.WORKER_HEARTBEAT_INTERVAL_SECONDS", 0),
            patch("fathom.orchestration.runner.process_job", side_effect=blocked_process),
            patch("fathom.orchestration.runner.renew_job_lease", side_effect=lose_lease),
        ):
            with self.assertRaises(JobLeaseLostError):
                await _run_job_with_heartbeat(job, settings, admin_client)

        self.assertTrue(processing_cancelled.is_set())


if __name__ == "__main__":
    unittest.main()

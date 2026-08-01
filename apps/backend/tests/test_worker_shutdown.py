from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from fathom.core.config import (
    DEFAULT_WORKER_SHUTDOWN_GRACE_SECONDS,
    Settings,
)
from fathom.orchestration.runner import (
    _run_job_with_heartbeat,
    _run_loop,
    _shutdown_running_tasks,
    _wait_for_job_notification,
)
from supabase import AsyncClient


class WorkerShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_drains_job_that_finishes_within_grace_period(self) -> None:
        completed = asyncio.Event()

        async def finish() -> None:
            await asyncio.sleep(0)
            completed.set()

        tasks = {asyncio.create_task(finish())}

        await _shutdown_running_tasks(tasks, grace_seconds=1)

        self.assertTrue(completed.is_set())
        self.assertEqual(tasks, set())

    async def test_shutdown_cancels_job_after_grace_period(self) -> None:
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def wait_forever() -> None:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        task = asyncio.create_task(wait_forever())
        tasks = {task}
        await started.wait()

        await _shutdown_running_tasks(tasks, grace_seconds=0)

        self.assertTrue(task.cancelled())
        self.assertTrue(cancelled.is_set())
        self.assertEqual(tasks, set())

    async def test_job_cancellation_stops_processing_and_heartbeat_children(self) -> None:
        processing_started = asyncio.Event()
        heartbeat_started = asyncio.Event()
        processing_cancelled = asyncio.Event()
        heartbeat_cancelled = asyncio.Event()

        async def processing(*_args: object) -> None:
            processing_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                processing_cancelled.set()

        async def heartbeat(*_args: object, **_kwargs: object) -> None:
            heartbeat_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                heartbeat_cancelled.set()

        settings = cast(Settings, SimpleNamespace())
        admin_client = cast(AsyncClient, object())
        job = {
            "id": "11111111-1111-1111-1111-111111111111",
            "lease_token": "22222222-2222-2222-2222-222222222222",
        }

        with (
            patch("fathom.orchestration.runner.process_job", processing),
            patch("fathom.orchestration.runner._maintain_job_lease", heartbeat),
        ):
            task = asyncio.create_task(_run_job_with_heartbeat(job, settings, admin_client))
            await processing_started.wait()
            await heartbeat_started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        self.assertTrue(processing_cancelled.is_set())
        self.assertTrue(heartbeat_cancelled.is_set())

    async def test_shutdown_event_interrupts_notification_wait(self) -> None:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        shutdown_event = asyncio.Event()
        shutdown_event.set()

        notified = await _wait_for_job_notification(
            queue,
            timeout_seconds=60,
            shutdown_event=shutdown_event,
        )

        self.assertFalse(notified)

    async def test_pre_requested_shutdown_does_not_claim_new_jobs(self) -> None:
        settings = cast(
            Settings,
            SimpleNamespace(
                worker_max_concurrent_jobs=1,
                worker_shutdown_grace_seconds=0,
            ),
        )
        shutdown_event = asyncio.Event()
        shutdown_event.set()

        with (
            patch(
                "fathom.orchestration.runner.create_supabase_admin_client",
                AsyncMock(return_value=cast(AsyncClient, object())),
            ),
            patch(
                "fathom.orchestration.runner.claim_next_job",
                AsyncMock(),
            ) as claim,
        ):
            await _run_loop(settings, shutdown_event=shutdown_event)

        claim.assert_not_awaited()


class WorkerShutdownSettingsTests(unittest.TestCase):
    def _settings_values(self) -> dict[str, str]:
        return {
            "OPENROUTER_API_KEY": "openrouter",
            "GROQ_API_KEY": "groq",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "publishable",
            "SUPABASE_SECRET_KEY": "secret",
            "APP_ENV": "local",
            "RATE_LIMIT": "0",
            "CORS_ALLOW_ORIGINS": "",
        }

    def test_shutdown_grace_has_bounded_default(self) -> None:
        settings = Settings.model_validate(self._settings_values())

        self.assertEqual(
            settings.worker_shutdown_grace_seconds,
            DEFAULT_WORKER_SHUTDOWN_GRACE_SECONDS,
        )

    def test_shutdown_grace_accepts_immediate_stop_and_rejects_excessive_values(self) -> None:
        values = self._settings_values()
        values["WORKER_SHUTDOWN_GRACE_SECONDS"] = "0"
        settings = Settings.model_validate(values)
        self.assertEqual(settings.worker_shutdown_grace_seconds, 0)

        values["WORKER_SHUTDOWN_GRACE_SECONDS"] = "301"
        with self.assertRaises(ValidationError):
            Settings.model_validate(values)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import asyncio
import time
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from fathom.core.config import (
    DEFAULT_WORKER_SHUTDOWN_GRACE_SECONDS,
    Settings,
)
from fathom.orchestration.runner import (
    _run_job_listener,
    _run_job_with_heartbeat,
    _run_loop,
    _run_scheduled_maintenance,
    _shutdown_billing_maintenance_task,
    _shutdown_running_tasks,
    _wait_for_signal,
    _wait_for_work,
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
        signal: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        shutdown_event = asyncio.Event()
        shutdown_event.set()

        notified = await _wait_for_signal(cast(Any, signal), shutdown_event)

        self.assertIsNone(notified)

    async def test_listener_wakes_scheduler_after_connect_and_notification(self) -> None:
        signal: asyncio.Queue[str] = asyncio.Queue(maxsize=1)

        @asynccontextmanager
        async def listen(*_args: object, **_kwargs: object):
            yield signal

        async def observe_wakes() -> None:
            await asyncio.wait_for(wake_event.wait(), timeout=1)
            self.assertTrue(wake_event.is_set())
            wake_event.clear()
            signal.put_nowait("notification")
            await asyncio.wait_for(wake_event.wait(), timeout=1)
            self.assertTrue(wake_event.is_set())
            shutdown_event.set()

        settings = cast(Settings, SimpleNamespace())
        wake_event = asyncio.Event()
        shutdown_event = asyncio.Event()
        with patch("fathom.orchestration.runner.listen_for_notifications", listen):
            await asyncio.gather(
                _run_job_listener(
                    settings,
                    wake_event=wake_event,
                    shutdown_event=shutdown_event,
                ),
                observe_wakes(),
            )

    async def test_listener_failure_uses_backoff_reconciliation_wake(self) -> None:
        @asynccontextmanager
        async def failed_listener(*_args: object, **_kwargs: object):
            raise ConnectionError("listener unavailable")
            yield  # pragma: no cover

        async def stop_after_first_delay(shutdown_event: asyncio.Event, _timeout: float) -> bool:
            shutdown_event.set()
            return True

        settings = cast(Settings, SimpleNamespace())
        wake_event = asyncio.Event()
        shutdown_event = asyncio.Event()
        with (
            patch("fathom.orchestration.runner.listen_for_notifications", failed_listener),
            patch("fathom.orchestration.runner._wait_for_shutdown", side_effect=stop_after_first_delay),
        ):
            await _run_job_listener(
                settings,
                wake_event=wake_event,
                shutdown_event=shutdown_event,
            )

        self.assertTrue(wake_event.is_set())

    async def test_maintenance_timeout_does_not_request_a_queue_claim(self) -> None:
        claim_requested = await _wait_for_work(
            wake_event=asyncio.Event(),
            shutdown_event=asyncio.Event(),
            running_tasks=set(),
            billing_maintenance_task=None,
            timeout_seconds=0,
            next_queue_wake_at=None,
        )

        self.assertFalse(claim_requested)

    async def test_durable_retry_deadline_requests_a_queue_claim(self) -> None:
        claim_requested = await _wait_for_work(
            wake_event=asyncio.Event(),
            shutdown_event=asyncio.Event(),
            running_tasks=set(),
            billing_maintenance_task=None,
            timeout_seconds=60,
            next_queue_wake_at=time.monotonic(),
        )

        self.assertTrue(claim_requested)

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

    async def test_billing_maintenance_runs_without_delaying_worker_loop(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def run_maintenance(*_args: object, **_kwargs: object) -> dict[str, int]:
            started.set()
            await release.wait()
            return {"maintenance_skipped": 0}

        settings = cast(Settings, SimpleNamespace())
        admin_client = cast(AsyncClient, object())
        with (
            patch("fathom.orchestration.runner.time.monotonic", return_value=100.0),
            patch("fathom.orchestration.runner.run_billing_maintenance", side_effect=run_maintenance),
        ):
            _, last_billing_at, task, work_requeued = await _run_scheduled_maintenance(
                admin_client,
                settings=settings,
                last_sweep_at=100.0,
                last_billing_maintenance_at=0.0,
                billing_maintenance_task=None,
            )

        await started.wait()
        self.assertEqual(last_billing_at, 100.0)
        self.assertFalse(work_requeued)
        self.assertIsNotNone(task)
        assert task is not None
        self.assertFalse(task.done())

        release.set()
        await task

    async def test_billing_maintenance_passes_never_overlap(self) -> None:
        release = asyncio.Event()

        async def existing_maintenance() -> dict[str, int]:
            await release.wait()
            return {"maintenance_skipped": 0}

        existing_task = asyncio.create_task(existing_maintenance())
        settings = cast(Settings, SimpleNamespace())
        admin_client = cast(AsyncClient, object())
        with (
            patch("fathom.orchestration.runner.time.monotonic", return_value=100.0),
            patch("fathom.orchestration.runner.run_billing_maintenance", AsyncMock()) as run_maintenance,
        ):
            _, last_billing_at, returned_task, work_requeued = await _run_scheduled_maintenance(
                admin_client,
                settings=settings,
                last_sweep_at=100.0,
                last_billing_maintenance_at=0.0,
                billing_maintenance_task=existing_task,
            )

        self.assertEqual(last_billing_at, 0.0)
        self.assertFalse(work_requeued)
        self.assertIs(returned_task, existing_task)
        run_maintenance.assert_not_called()

        release.set()
        await existing_task

    async def test_shutdown_cancels_billing_maintenance(self) -> None:
        cancelled = asyncio.Event()

        async def blocked_maintenance() -> dict[str, int]:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        task = asyncio.create_task(blocked_maintenance())
        await asyncio.sleep(0)

        await _shutdown_billing_maintenance_task(task)

        self.assertTrue(task.cancelled())
        self.assertTrue(cancelled.is_set())


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

    def test_worker_concurrency_is_bounded(self) -> None:
        values = self._settings_values()
        values["WORKER_MAX_CONCURRENT_JOBS"] = "64"
        self.assertEqual(Settings.model_validate(values).worker_max_concurrent_jobs, 64)

        for invalid_value in ("0", "65"):
            values["WORKER_MAX_CONCURRENT_JOBS"] = invalid_value
            with self.subTest(invalid_value=invalid_value), self.assertRaises(ValidationError):
                Settings.model_validate(values)

    def test_billing_debt_window_is_bounded(self) -> None:
        values = self._settings_values()
        values["BILLING_DEBT_CAP_SECONDS"] = "0"
        self.assertEqual(Settings.model_validate(values).billing_debt_cap_seconds, 0)

        for invalid_value in ("-1", "86401"):
            values["BILLING_DEBT_CAP_SECONDS"] = invalid_value
            with self.subTest(invalid_value=invalid_value), self.assertRaises(ValidationError):
                Settings.model_validate(values)


if __name__ == "__main__":
    unittest.main()

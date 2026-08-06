from __future__ import annotations

import asyncio
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from fathom.application.briefings.sessions.event_coordinator import JobEventCoordinator
from fathom.core.config import Settings


@asynccontextmanager
async def _quiet_listener(_settings: Settings, _channel: str):
    yield asyncio.Queue()


class JobEventCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.settings = cast(Settings, SimpleNamespace())
        self.admin_client = object()

    async def test_coalesces_one_job_fetch_and_fans_out_to_matching_tabs(self) -> None:
        event = {"sequence_id": 11, "event_type": "transcription_completed"}
        fetch = AsyncMock(return_value=[event])
        coordinator = JobEventCoordinator(self.settings, self.admin_client, safety_reconcile_seconds=3600)

        with (
            patch(
                "fathom.application.briefings.sessions.event_coordinator.listen_for_job_event_notifications",
                _quiet_listener,
            ),
            patch(
                "fathom.application.briefings.sessions.event_coordinator.list_job_events_after",
                fetch,
            ),
        ):
            await coordinator.start()
            try:
                while not coordinator.listener_healthy:
                    await asyncio.sleep(0)
                async with (
                    coordinator.subscribe("job-1", cursor=10) as first_tab,
                    coordinator.subscribe("job-1", cursor=10) as second_tab,
                    coordinator.subscribe("job-2", cursor=4) as other_job,
                ):
                    coordinator.request_refresh("job-1", reason="notification")
                    coordinator.request_refresh("job-1", reason="notification")

                    first_update, second_update = await asyncio.gather(
                        first_tab.wait(0.5),
                        second_tab.wait(0.5),
                    )
                    self.assertIsNotNone(first_update)
                    self.assertEqual(first_update, second_update)
                    self.assertEqual(first_update.events, (event,))
                    self.assertIsNone(await other_job.wait(0.01))
                    fetch.assert_awaited_once_with(
                        self.admin_client,
                        job_id="job-1",
                        after_sequence_id=10,
                        limit=100,
                    )
            finally:
                await coordinator.close()

    async def test_slow_subscriber_merges_bursts_without_blocking_dispatch(self) -> None:
        first_fetched = asyncio.Event()
        fetch_count = 0

        async def fetch_events(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            nonlocal fetch_count
            fetch_count += 1
            first_fetched.set()
            if fetch_count == 1:
                return [{"sequence_id": 1, "event_type": "job_claimed"}]
            return [
                {"sequence_id": 1, "event_type": "job_claimed"},
                {"sequence_id": 2, "event_type": "transcription_started"},
            ]

        coordinator = JobEventCoordinator(self.settings, self.admin_client, safety_reconcile_seconds=3600)
        with (
            patch(
                "fathom.application.briefings.sessions.event_coordinator.listen_for_job_event_notifications",
                _quiet_listener,
            ),
            patch(
                "fathom.application.briefings.sessions.event_coordinator.list_job_events_after",
                AsyncMock(side_effect=fetch_events),
            ),
        ):
            await coordinator.start()
            try:
                async with coordinator.subscribe("job-1", cursor=0) as subscription:
                    coordinator.request_refresh("job-1", reason="notification")
                    await asyncio.wait_for(first_fetched.wait(), timeout=0.5)
                    while fetch_count < 1:
                        await asyncio.sleep(0)

                    coordinator.request_refresh("job-1", reason="notification")
                    while fetch_count < 2:
                        await asyncio.sleep(0)

                    update = await subscription.wait(0.5)
                    self.assertIsNotNone(update)
                    self.assertEqual([event["sequence_id"] for event in update.events], [1, 2])
            finally:
                await coordinator.close()

    async def test_each_replica_fetches_once_and_fans_out_only_to_its_local_streams(self) -> None:
        event = {"sequence_id": 21, "event_type": "summary_started"}
        fetch = AsyncMock(return_value=[event])
        first_client = object()
        second_client = object()
        first_replica = JobEventCoordinator(self.settings, first_client, safety_reconcile_seconds=3600)
        second_replica = JobEventCoordinator(self.settings, second_client, safety_reconcile_seconds=3600)

        with (
            patch(
                "fathom.application.briefings.sessions.event_coordinator.listen_for_job_event_notifications",
                _quiet_listener,
            ),
            patch(
                "fathom.application.briefings.sessions.event_coordinator.list_job_events_after",
                fetch,
            ),
        ):
            await first_replica.start()
            await second_replica.start()
            try:
                while not first_replica.listener_healthy or not second_replica.listener_healthy:
                    await asyncio.sleep(0)
                async with (
                    first_replica.subscribe("job-1", cursor=20) as first_stream,
                    second_replica.subscribe("job-1", cursor=20) as second_stream,
                ):
                    first_replica.request_refresh("job-1", reason="notification")
                    second_replica.request_refresh("job-1", reason="notification")
                    first_update, second_update = await asyncio.gather(
                        first_stream.wait(0.5),
                        second_stream.wait(0.5),
                    )

                    self.assertEqual(first_update, second_update)
                    self.assertEqual(fetch.await_count, 2)
                    self.assertEqual(
                        {call.args[0] for call in fetch.await_args_list},
                        {first_client, second_client},
                    )
            finally:
                await first_replica.close()
                await second_replica.close()

    async def test_fallback_reconciliation_runs_only_when_listener_is_unhealthy(self) -> None:
        event = {"sequence_id": 7, "event_type": "summary_completed"}
        fetch = AsyncMock(return_value=[event])
        coordinator = JobEventCoordinator(self.settings, self.admin_client, safety_reconcile_seconds=0.01)
        with (
            patch(
                "fathom.application.briefings.sessions.event_coordinator.listen_for_job_event_notifications",
                _quiet_listener,
            ),
            patch(
                "fathom.application.briefings.sessions.event_coordinator.list_job_events_after",
                fetch,
            ),
        ):
            await coordinator.start()
            try:
                while not coordinator.listener_healthy:
                    await asyncio.sleep(0)
                async with coordinator.subscribe("job-1", cursor=6) as subscription:
                    coordinator.listener_healthy = False
                    update = await subscription.wait(0.5)
                    self.assertIsNotNone(update)
                    self.assertEqual(update.events, (event,))
                    self.assertTrue(update.reconcile_snapshot)
            finally:
                await coordinator.close()

    async def test_healthy_listener_does_not_poll_subscribed_jobs(self) -> None:
        fetch = AsyncMock(return_value=[])
        coordinator = JobEventCoordinator(self.settings, self.admin_client, safety_reconcile_seconds=0.01)
        with (
            patch(
                "fathom.application.briefings.sessions.event_coordinator.listen_for_job_event_notifications",
                _quiet_listener,
            ),
            patch(
                "fathom.application.briefings.sessions.event_coordinator.list_job_events_after",
                fetch,
            ),
        ):
            await coordinator.start()
            try:
                while not coordinator.listener_healthy:
                    await asyncio.sleep(0)
                async with coordinator.subscribe("job-1", cursor=0):
                    await asyncio.sleep(0.05)
                fetch.assert_not_awaited()
                self.assertEqual(coordinator.status_snapshot()["fallback_reconciliations"], 0)
            finally:
                await coordinator.close()

    async def test_overflow_signal_reconciles_every_subscribed_job(self) -> None:
        notifications: asyncio.Queue[str] = asyncio.Queue()

        @asynccontextmanager
        async def overflow_listener(_settings: Settings, _channel: str):
            yield notifications

        fetch = AsyncMock(return_value=[])
        coordinator = JobEventCoordinator(self.settings, self.admin_client, safety_reconcile_seconds=3600)
        with (
            patch(
                "fathom.application.briefings.sessions.event_coordinator.listen_for_job_event_notifications",
                overflow_listener,
            ),
            patch(
                "fathom.application.briefings.sessions.event_coordinator.list_job_events_after",
                fetch,
            ),
        ):
            await coordinator.start()
            try:
                while not coordinator.listener_healthy:
                    await asyncio.sleep(0)
                async with (
                    coordinator.subscribe("job-1", cursor=0) as first,
                    coordinator.subscribe("job-2", cursor=0) as second,
                ):
                    notifications.put_nowait("overflow")
                    await asyncio.gather(first.wait(0.5), second.wait(0.5))
                    self.assertEqual(fetch.await_count, 2)
                    self.assertEqual(coordinator.status_snapshot()["notification_overflows"], 1)
            finally:
                await coordinator.close()

    async def test_slow_job_does_not_block_another_job(self) -> None:
        slow_started = asyncio.Event()
        release_slow = asyncio.Event()

        async def fetch_events(_client: object, *, job_id: str, **_kwargs: Any) -> list[dict[str, Any]]:
            if job_id == "job-1":
                slow_started.set()
                await release_slow.wait()
            return [{"sequence_id": 1, "event_type": "job_claimed"}]

        coordinator = JobEventCoordinator(self.settings, self.admin_client, safety_reconcile_seconds=3600)
        with (
            patch(
                "fathom.application.briefings.sessions.event_coordinator.listen_for_job_event_notifications",
                _quiet_listener,
            ),
            patch(
                "fathom.application.briefings.sessions.event_coordinator.list_job_events_after",
                AsyncMock(side_effect=fetch_events),
            ),
        ):
            await coordinator.start()
            try:
                async with (
                    coordinator.subscribe("job-1", cursor=0) as slow,
                    coordinator.subscribe("job-2", cursor=0) as fast,
                ):
                    coordinator.request_refresh("job-1", reason="notification")
                    coordinator.request_refresh("job-2", reason="notification")
                    await asyncio.wait_for(slow_started.wait(), timeout=0.5)
                    self.assertIsNotNone(await fast.wait(0.5))
                    self.assertIsNone(await slow.wait(0.01))
                    release_slow.set()
                    self.assertIsNotNone(await slow.wait(0.5))
            finally:
                release_slow.set()
                await coordinator.close()

    async def test_listener_disconnect_is_supervised_and_reconnected(self) -> None:
        connection_count = 0
        reconnected = asyncio.Event()

        @asynccontextmanager
        async def reconnecting_listener(_settings: Settings, _channel: str):
            nonlocal connection_count
            connection_count += 1
            queue: asyncio.Queue[str] = asyncio.Queue()
            if connection_count == 1:
                queue.put_nowait("disconnected")
            else:
                reconnected.set()
            yield queue

        coordinator = JobEventCoordinator(self.settings, self.admin_client, safety_reconcile_seconds=3600)
        with (
            patch(
                "fathom.application.briefings.sessions.event_coordinator.listen_for_job_event_notifications",
                reconnecting_listener,
            ),
            patch(
                "fathom.application.briefings.sessions.event_coordinator.LISTENER_RECONNECT_BASE_SECONDS",
                0.001,
            ),
        ):
            await coordinator.start()
            try:
                await asyncio.wait_for(reconnected.wait(), timeout=0.5)
                self.assertEqual(connection_count, 2)
                self.assertTrue(coordinator.listener_healthy)
            finally:
                await coordinator.close()


if __name__ == "__main__":
    unittest.main()

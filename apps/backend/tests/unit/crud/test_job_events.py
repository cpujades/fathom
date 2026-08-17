from __future__ import annotations

import logging
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fathom.crud.supabase.job_events import (
    fetch_latest_job_event_sequence,
    list_job_events_after,
    record_job_event,
    record_job_event_best_effort,
)


class JobEventCrudTests(unittest.IsolatedAsyncioTestCase):
    async def test_record_job_event_upserts_with_stable_id(self) -> None:
        client = MagicMock()
        query = MagicMock()
        client.table.return_value = query
        query.upsert.return_value = query
        query.execute = AsyncMock(return_value=SimpleNamespace(data=[]))

        event_id = await record_job_event(
            client,
            job_id="job-1",
            event_type="provider_started",
            event_id="event-1",
        )

        self.assertEqual(event_id, "event-1")
        query.upsert.assert_called_once_with(
            {
                "id": "event-1",
                "job_id": "job-1",
                "event_type": "provider_started",
                "metadata": {},
            },
            on_conflict="id",
            ignore_duplicates=True,
        )

    async def test_best_effort_retry_reuses_id_and_succeeds(self) -> None:
        logger = MagicMock(spec=logging.Logger)
        record = AsyncMock(side_effect=[RuntimeError("temporary"), None])

        with (
            patch("fathom.crud.supabase.job_events.record_job_event", record),
            patch("fathom.crud.supabase.job_events.asyncio.sleep", AsyncMock()) as sleep,
        ):
            result = await record_job_event_best_effort(
                MagicMock(),
                logger,
                job_id="job-1",
                event_type="provider_started",
            )

        self.assertTrue(result)
        self.assertEqual(record.await_count, 2)
        first_id = record.await_args_list[0].kwargs["event_id"]
        self.assertEqual(record.await_args_list[1].kwargs["event_id"], first_id)
        logger.warning.assert_called_once()
        logger.error.assert_not_called()
        sleep.assert_awaited_once_with(0.05)

    async def test_best_effort_failure_is_visible_and_bounded(self) -> None:
        logger = MagicMock(spec=logging.Logger)
        record = AsyncMock(side_effect=RuntimeError("database unavailable"))

        with (
            patch("fathom.crud.supabase.job_events.record_job_event", record),
            patch("fathom.crud.supabase.job_events.asyncio.sleep", AsyncMock()),
        ):
            result = await record_job_event_best_effort(
                MagicMock(),
                logger,
                job_id="job-1",
                event_type="provider_started",
                max_attempts=3,
            )

        self.assertFalse(result)
        self.assertEqual(record.await_count, 3)
        ids = {call.kwargs["event_id"] for call in record.await_args_list}
        self.assertEqual(len(ids), 1)
        self.assertEqual(logger.warning.call_count, 2)
        logger.error.assert_called_once()

    async def test_list_after_uses_ordered_bounded_cursor_query(self) -> None:
        client = MagicMock()
        query = MagicMock()
        client.table.return_value = query
        query.select.return_value = query
        query.eq.return_value = query
        query.gt.return_value = query
        query.order.return_value = query
        query.limit.return_value = query
        query.execute = AsyncMock(
            return_value=SimpleNamespace(data=[{"sequence_id": 8, "event_type": "job_state_changed"}])
        )

        events = await list_job_events_after(
            client,
            job_id="job-1",
            after_sequence_id=7,
            limit=999,
        )

        self.assertEqual(events[0]["sequence_id"], 8)
        query.eq.assert_called_once_with("job_id", "job-1")
        query.gt.assert_called_once_with("sequence_id", 7)
        query.order.assert_called_once_with("sequence_id", desc=False)
        query.limit.assert_called_once_with(100)

    async def test_latest_sequence_returns_zero_when_no_events(self) -> None:
        client = MagicMock()
        query = MagicMock()
        client.table.return_value = query
        query.select.return_value = query
        query.eq.return_value = query
        query.order.return_value = query
        query.limit.return_value = query
        query.execute = AsyncMock(return_value=SimpleNamespace(data=[]))

        self.assertEqual(await fetch_latest_job_event_sequence(client, job_id="job-1"), 0)


if __name__ == "__main__":
    unittest.main()

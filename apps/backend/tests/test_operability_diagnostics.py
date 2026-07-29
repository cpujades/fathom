from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from fathom.application.diagnostics.operability import fetch_operability_report


class OperabilityDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def test_builds_bounded_privacy_safe_report(self) -> None:
        connection = AsyncMock()
        connection.fetchrow.return_value = {
            "generated_at": datetime(2026, 7, 29, tzinfo=UTC),
            "overdue_queued_jobs": 2,
            "expired_running_leases": 1,
            "missing_running_leases": 0,
            "orphaned_pending_summaries": 1,
            "terminal_jobs_missing_settlement": 1,
            "settlement_balance_mismatches": 0,
            "unresolved_webhook_events": 2,
            "stale_processing_webhook_events": 1,
            "job_ids": ["job-1", "job-2", "job-3"],
            "summary_ids": ["summary-1"],
            "provider_event_ids": ["event-1", "event-2"],
            "user_id": "must-not-appear",
            "summary_markdown": "must-not-appear",
        }

        report = await fetch_operability_report(connection, stale_minutes=10, sample_limit=2)

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["stale_after_minutes"], 10)
        self.assertEqual(report["counts"]["overdue_queued_jobs"], 2)
        self.assertEqual(report["samples"]["job_ids"], ["job-1", "job-2"])
        self.assertNotIn("user_id", report)
        self.assertNotIn("summary_markdown", report)
        connection.fetchrow.assert_awaited_once()

    async def test_reports_ok_when_all_counts_are_zero(self) -> None:
        connection = AsyncMock()
        connection.fetchrow.return_value = {}

        report = await fetch_operability_report(connection)

        self.assertEqual(report["status"], "ok")
        self.assertTrue(all(value == 0 for value in report["counts"].values()))

    async def test_rejects_unbounded_inputs_before_querying(self) -> None:
        connection = AsyncMock()

        for stale_minutes, sample_limit in ((0, 10), (1_441, 10), (5, 0), (5, 101)):
            with self.subTest(stale_minutes=stale_minutes, sample_limit=sample_limit):
                with self.assertRaises(ValueError):
                    await fetch_operability_report(
                        connection,
                        stale_minutes=stale_minutes,
                        sample_limit=sample_limit,
                    )

        connection.fetchrow.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

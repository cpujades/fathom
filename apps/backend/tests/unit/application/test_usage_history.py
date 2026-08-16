from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fathom.application.usage import _get_usage_history


class UsageHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_uses_settlements_and_keeps_archived_usage(self) -> None:
        admin_client = object()
        entries = [
            {
                "job_id": "11111111-1111-1111-1111-111111111111",
                "duration_seconds": 180,
                "subscription_seconds": 100,
                "pack_seconds": 80,
                "debt_incurred_seconds": 0,
                "settled_at": "2026-08-15T10:00:00+00:00",
            },
            {
                "job_id": "22222222-2222-2222-2222-222222222222",
                "duration_seconds": 60,
                "subscription_seconds": 0,
                "pack_seconds": 0,
                "debt_incurred_seconds": 60,
                "settled_at": "2026-08-14T10:00:00+00:00",
            },
            {
                "job_id": "77777777-7777-7777-7777-777777777777",
                "duration_seconds": 30,
                "subscription_seconds": 30,
                "pack_seconds": 0,
                "debt_incurred_seconds": 0,
                "settled_at": "2026-08-13T10:00:00+00:00",
            },
        ]
        jobs = [
            {
                "id": entries[0]["job_id"],
                "status": "succeeded",
                "summary_id": "33333333-3333-3333-3333-333333333333",
            },
            {
                "id": entries[1]["job_id"],
                "status": "deleted",
                "summary_id": "44444444-4444-4444-4444-444444444444",
            },
        ]
        summaries = [
            {
                "id": jobs[0]["summary_id"],
                "transcript_id": "55555555-5555-5555-5555-555555555555",
            },
            {
                "id": jobs[1]["summary_id"],
                "transcript_id": "66666666-6666-6666-6666-666666666666",
            },
        ]
        transcripts = [
            {"id": summaries[0]["transcript_id"], "source_title": "Active briefing"},
            {"id": summaries[1]["transcript_id"], "source_title": "Archived briefing"},
        ]

        with (
            patch(
                "fathom.application.usage.fetch_usage_settlements",
                AsyncMock(return_value=entries),
            ) as fetch_settlements,
            patch("fathom.application.usage.fetch_jobs_by_ids", AsyncMock(return_value=jobs)),
            patch("fathom.application.usage.fetch_summaries_by_ids", AsyncMock(return_value=summaries)),
            patch("fathom.application.usage.fetch_transcripts_by_ids", AsyncMock(return_value=transcripts)),
        ):
            result = await _get_usage_history("user-1", admin_client, limit=2, offset=4)

        fetch_settlements.assert_awaited_once_with(admin_client, user_id="user-1", limit=3, offset=4)
        self.assertEqual(result.limit, 2)
        self.assertEqual(result.offset, 4)
        self.assertTrue(result.has_more)
        self.assertEqual(len(result.entries), 2)
        self.assertEqual(result.entries[0]["title"], "Active briefing")
        self.assertEqual(
            result.entries[0]["session_path"],
            "/app/briefings/sessions/11111111-1111-1111-1111-111111111111",
        )
        self.assertEqual(result.entries[1]["title"], "Archived briefing")
        self.assertIsNone(result.entries[1]["session_path"])
        self.assertEqual(result.entries[1]["debt_incurred_seconds"], 60)


if __name__ == "__main__":
    unittest.main()

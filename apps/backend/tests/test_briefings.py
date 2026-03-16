from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

from fathom.application.briefings import list_briefings_for_user
from fathom.core.config import Settings


class BriefingLibraryTests(unittest.IsolatedAsyncioTestCase):
    async def test_lists_briefings_from_jobs_with_enriched_metadata(self) -> None:
        admin_client = object()
        settings = cast(Settings, SimpleNamespace())

        jobs = [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "summary_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "url": "https://www.youtube.com/watch?v=abc123",
                "created_at": "2026-03-15T10:00:00+00:00",
                "duration_seconds": 3660,
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "summary_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "url": "https://example.com/research/interview",
                "created_at": "2026-03-14T10:00:00+00:00",
                "duration_seconds": 1800,
            },
        ]
        summaries = [
            {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "transcript_id": "transcript-1"},
            {"id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "transcript_id": "transcript-2"},
        ]
        transcripts = [
            {
                "id": "transcript-1",
                "video_id": "abc123",
                "source_title": "The Founders Podcast",
                "source_author": "David Senra",
                "source_length_seconds": 3660,
            },
            {
                "id": "transcript-2",
                "video_id": None,
                "source_title": "AI Research Notes",
                "source_author": "Open Source Lab",
                "source_length_seconds": 1800,
            },
        ]

        with (
            patch("fathom.application.briefings.create_supabase_admin_client", AsyncMock(return_value=admin_client)),
            patch(
                "fathom.application.briefings.fetch_briefing_jobs_page",
                AsyncMock(return_value=(jobs, 2)),
            ) as fetch_jobs_mock,
            patch("fathom.application.briefings.fetch_summaries_by_ids", AsyncMock(return_value=summaries)),
            patch("fathom.application.briefings.fetch_transcripts_by_ids", AsyncMock(return_value=transcripts)),
        ):
            response = await list_briefings_for_user(user_id="user-123", settings=settings)

        fetch_jobs_mock.assert_awaited_once_with(
            admin_client,
            user_id="user-123",
            limit=24,
            offset=0,
            sort_desc=True,
        )
        self.assertEqual(response.total_count, 2)
        self.assertFalse(response.has_more)
        self.assertEqual(len(response.items), 2)
        self.assertEqual(response.items[0].title, "The Founders Podcast")
        self.assertEqual(response.items[0].author, "David Senra")
        self.assertEqual(response.items[0].source_type, "youtube")
        self.assertEqual(response.items[0].source_host, "youtube.com")
        self.assertEqual(response.items[0].session_path, "/app/briefings/sessions/11111111-1111-1111-1111-111111111111")
        self.assertEqual(response.items[0].source_duration_seconds, 3660)
        self.assertEqual(response.items[0].source_thumbnail_url, "https://i.ytimg.com/vi/abc123/hqdefault.jpg")
        self.assertEqual(response.items[1].source_host, "example.com")

    async def test_filters_briefings_by_query_and_source_type(self) -> None:
        admin_client = object()
        settings = cast(Settings, SimpleNamespace())

        jobs = [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "summary_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "url": "https://www.youtube.com/watch?v=abc123",
                "created_at": "2026-03-15T10:00:00+00:00",
                "duration_seconds": 3660,
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "summary_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "url": "https://example.com/research/interview",
                "created_at": "2026-03-14T10:00:00+00:00",
                "duration_seconds": 1800,
            },
        ]
        summaries = [
            {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "transcript_id": "transcript-1"},
            {"id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "transcript_id": "transcript-2"},
        ]
        transcripts = [
            {
                "id": "transcript-1",
                "video_id": "abc123",
                "source_title": "Lex Fridman with Demis Hassabis",
                "source_author": "Lex Fridman",
                "source_length_seconds": 3660,
            },
            {
                "id": "transcript-2",
                "video_id": None,
                "source_title": "AI Research Notes",
                "source_author": "Open Source Lab",
                "source_length_seconds": 1800,
            },
        ]

        with (
            patch("fathom.application.briefings.create_supabase_admin_client", AsyncMock(return_value=admin_client)),
            patch(
                "fathom.application.briefings.fetch_briefing_jobs_page",
                AsyncMock(return_value=(jobs, 2)),
            ) as fetch_jobs_mock,
            patch("fathom.application.briefings.fetch_summaries_by_ids", AsyncMock(return_value=summaries)),
            patch("fathom.application.briefings.fetch_transcripts_by_ids", AsyncMock(return_value=transcripts)),
        ):
            response = await list_briefings_for_user(
                user_id="user-123",
                settings=settings,
                query="lex",
                sort="oldest",
                source_type="youtube",
            )

        fetch_jobs_mock.assert_awaited_once_with(
            admin_client,
            user_id="user-123",
            limit=200,
            offset=0,
            sort_desc=False,
        )
        self.assertEqual(response.total_count, 1)
        self.assertEqual(len(response.items), 1)
        self.assertEqual(response.items[0].title, "Lex Fridman with Demis Hassabis")
        self.assertEqual(response.items[0].source_type, "youtube")
        self.assertEqual(response.query, "lex")
        self.assertEqual(response.sort, "oldest")
        self.assertEqual(response.source_type, "youtube")


if __name__ == "__main__":
    unittest.main()

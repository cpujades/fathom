from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fathom.api.deps.auth import AuthContext
from fathom.application.briefings import (
    _create_briefing_pdf,
    create_briefing_pdf,
    get_briefing,
    list_briefings_for_user,
)
from fathom.core.config import Settings
from fathom.core.constants import SUPABASE_PDF_BUCKET
from fathom.core.errors import NotReadyError
from fathom.crud.supabase.summaries import PdfPreparation
from fathom.services.pdf import PDF_CACHE_VERSION, PDF_RENDER_FAILED_MESSAGE, PDFBusyError, PDFError


class BriefingLibraryTests(unittest.IsolatedAsyncioTestCase):
    async def test_pdf_url_checks_owned_summary_before_admin_storage_access(self) -> None:
        settings = cast(Settings, SimpleNamespace())
        auth = AuthContext(access_token="access-token", user_id="user-123")
        briefing_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        user_client = object()
        admin_client = object()
        object_key = "user-123/video/briefing.pdf"

        with (
            patch(
                "fathom.application.briefings.create_supabase_user_client",
                AsyncMock(return_value=user_client),
            ),
            patch(
                "fathom.application.briefings.create_supabase_admin_client",
                AsyncMock(return_value=admin_client),
            ),
            patch(
                "fathom.application.briefings.fetch_summary",
                AsyncMock(
                    return_value={
                        "id": str(briefing_id),
                        "status": "ready",
                        "summary_markdown": "# Complete",
                        "pdf_object_key": object_key,
                        "pdf_cache_version": PDF_CACHE_VERSION,
                    }
                ),
            ) as fetch_summary,
            patch(
                "fathom.application.briefings.create_pdf_signed_url",
                AsyncMock(return_value="https://storage.example/signed"),
            ) as create_signed_url,
        ):
            response = await get_briefing(briefing_id, auth, settings)

        fetch_summary.assert_awaited_once_with(user_client, str(briefing_id))
        create_signed_url.assert_awaited_once()
        self.assertIs(create_signed_url.await_args.args[0], admin_client)
        self.assertEqual(response.pdf_url, "https://storage.example/signed")

    async def test_stale_cached_pdf_is_not_issued(self) -> None:
        settings = cast(Settings, SimpleNamespace())
        auth = AuthContext(access_token="access-token", user_id="user-123")
        briefing_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        user_client = object()

        with (
            patch(
                "fathom.application.briefings.create_supabase_user_client",
                AsyncMock(return_value=user_client),
            ),
            patch(
                "fathom.application.briefings.fetch_summary",
                AsyncMock(
                    return_value={
                        "id": str(briefing_id),
                        "status": "ready",
                        "summary_markdown": "# Complete",
                        "pdf_object_key": "user-123/video/legacy.pdf",
                        "pdf_cache_version": None,
                    }
                ),
            ),
            patch(
                "fathom.application.briefings.create_supabase_admin_client",
                AsyncMock(),
            ) as create_admin_client,
            patch(
                "fathom.application.briefings.create_pdf_signed_url",
                AsyncMock(),
            ) as create_signed_url,
        ):
            response = await get_briefing(briefing_id, auth, settings)

        self.assertIsNone(response.pdf_url)
        create_admin_client.assert_not_awaited()
        create_signed_url.assert_not_awaited()

    async def test_detail_rejects_pending_partial_summary(self) -> None:
        settings = cast(Settings, SimpleNamespace())
        auth = AuthContext(access_token="access-token", user_id="user-123")
        briefing_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        user_client = object()

        with (
            patch(
                "fathom.application.briefings.create_supabase_user_client",
                AsyncMock(return_value=user_client),
            ),
            patch(
                "fathom.application.briefings.fetch_summary",
                AsyncMock(
                    return_value={
                        "id": str(briefing_id),
                        "status": "pending",
                        "summary_markdown": "# Partial",
                    }
                ),
            ),
            patch(
                "fathom.application.briefings.create_supabase_admin_client",
                AsyncMock(),
            ) as create_admin_client,
        ):
            with self.assertRaises(NotReadyError):
                await get_briefing(briefing_id, auth, settings)

        create_admin_client.assert_not_awaited()

    async def test_pdf_rejects_pending_partial_summary_before_render_or_upload(self) -> None:
        settings = cast(Settings, SimpleNamespace())
        auth = AuthContext(access_token="access-token", user_id="user-123")
        briefing_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        user_client = object()

        with (
            patch(
                "fathom.application.briefings.create_supabase_user_client",
                AsyncMock(return_value=user_client),
            ),
            patch(
                "fathom.application.briefings.fetch_summary",
                AsyncMock(
                    return_value={
                        "id": str(briefing_id),
                        "status": "pending",
                        "summary_markdown": "# Partial",
                    }
                ),
            ),
            patch(
                "fathom.application.briefings.create_supabase_admin_client",
                AsyncMock(),
            ) as create_admin_client,
            patch("fathom.application.briefings.render_markdown_pdf_bytes", AsyncMock()) as render_pdf,
            patch("fathom.application.briefings.upload_pdf", AsyncMock()) as upload_pdf,
        ):
            with self.assertRaises(NotReadyError):
                await create_briefing_pdf(briefing_id, auth, settings)

        create_admin_client.assert_not_awaited()
        render_pdf.assert_not_awaited()
        upload_pdf.assert_not_awaited()

    async def test_pdf_generation_returns_busy_without_rendering_when_claim_is_live(self) -> None:
        briefing_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        summary = {
            "id": str(briefing_id),
            "user_id": "user-123",
            "transcript_id": "transcript-123",
            "summary_markdown": "# Complete",
        }
        admin_client = object()

        with (
            patch(
                "fathom.application.briefings.prepare_summary_pdf",
                AsyncMock(
                    return_value=PdfPreparation(
                        resolution_type="in_progress",
                        pdf_object_key=None,
                    )
                ),
            ),
            patch(
                "fathom.application.briefings.render_markdown_pdf_bytes",
                AsyncMock(),
            ) as render_pdf,
            patch(
                "fathom.application.briefings.upload_pdf",
                AsyncMock(),
            ) as upload_pdf,
        ):
            with self.assertRaises(PDFBusyError):
                await _create_briefing_pdf(
                    briefing_id,
                    str(briefing_id),
                    summary,
                    admin_client,
                )

        render_pdf.assert_not_awaited()
        upload_pdf.assert_not_awaited()

    async def test_stale_pdf_is_regenerated_with_current_cache_version(self) -> None:
        briefing_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        summary = {
            "id": str(briefing_id),
            "user_id": "user-123",
            "transcript_id": "transcript-123",
            "summary_markdown": "# Complete",
            "pdf_object_key": "user-123/video/legacy.pdf",
            "pdf_cache_version": None,
        }
        admin_client = object()

        with (
            patch(
                "fathom.application.briefings.prepare_summary_pdf",
                AsyncMock(
                    return_value=PdfPreparation(
                        resolution_type="acquired",
                        pdf_object_key=None,
                    )
                ),
            ),
            patch(
                "fathom.application.briefings.render_markdown_pdf_bytes",
                AsyncMock(return_value=b"%PDF-current"),
            ) as render_pdf,
            patch(
                "fathom.application.briefings.fetch_transcript_by_id",
                AsyncMock(return_value={"video_id": "video-123"}),
            ),
            patch(
                "fathom.application.briefings.upload_pdf",
                AsyncMock(),
            ) as upload_pdf,
            patch(
                "fathom.application.briefings.complete_summary_pdf",
                AsyncMock(return_value=True),
            ) as complete_pdf,
            patch(
                "fathom.application.briefings.fail_summary_pdf",
                AsyncMock(return_value=False),
            ) as fail_pdf,
            patch(
                "fathom.application.briefings.create_pdf_signed_url",
                AsyncMock(return_value="https://storage.example/current"),
            ),
            patch(
                "fathom.application.briefings.delete_object",
                AsyncMock(),
            ) as delete_pdf,
        ):
            response = await _create_briefing_pdf(
                briefing_id,
                str(briefing_id),
                summary,
                admin_client,
            )

        expected_key = upload_pdf.await_args.kwargs["object_key"]
        self.assertRegex(
            expected_key,
            rf"^user-123/video-123/v{PDF_CACHE_VERSION}/{briefing_id}/"
            r"[0-9a-f-]{36}\.pdf$",
        )
        self.assertEqual(response.pdf_url, "https://storage.example/current")
        render_pdf.assert_awaited_once_with("# Complete")
        self.assertEqual(upload_pdf.await_args.kwargs["object_key"], expected_key)
        self.assertEqual(complete_pdf.await_args.kwargs["pdf_object_key"], expected_key)
        self.assertEqual(complete_pdf.await_args.kwargs["cache_version"], PDF_CACHE_VERSION)
        fail_pdf.assert_not_awaited()
        delete_pdf.assert_not_awaited()

    async def test_stale_pdf_renderer_cannot_overwrite_or_publish_the_winner(self) -> None:
        briefing_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        winner_token = UUID("11111111-1111-1111-1111-111111111111")
        stale_token = UUID("22222222-2222-2222-2222-222222222222")
        summary = {
            "id": str(briefing_id),
            "user_id": "user-123",
            "transcript_id": "transcript-123",
            "summary_markdown": "# Complete",
        }
        admin_client = object()

        with (
            patch(
                "fathom.application.briefings.uuid4",
                side_effect=[winner_token, stale_token],
            ),
            patch(
                "fathom.application.briefings.prepare_summary_pdf",
                AsyncMock(
                    side_effect=[
                        PdfPreparation(resolution_type="acquired", pdf_object_key=None),
                        PdfPreparation(resolution_type="acquired", pdf_object_key=None),
                    ]
                ),
            ),
            patch(
                "fathom.application.briefings.render_markdown_pdf_bytes",
                AsyncMock(side_effect=[b"%PDF-winner", b"%PDF-stale"]),
            ),
            patch(
                "fathom.application.briefings.fetch_transcript_by_id",
                AsyncMock(return_value={"video_id": "video-123"}),
            ),
            patch(
                "fathom.application.briefings.upload_pdf",
                AsyncMock(),
            ) as upload_pdf,
            patch(
                "fathom.application.briefings.complete_summary_pdf",
                AsyncMock(side_effect=[True, False]),
            ) as complete_pdf,
            patch(
                "fathom.application.briefings.fail_summary_pdf",
                AsyncMock(return_value=False),
            ),
            patch(
                "fathom.application.briefings.create_pdf_signed_url",
                AsyncMock(return_value="https://storage.example/winner"),
            ),
            patch(
                "fathom.application.briefings.delete_object",
                AsyncMock(),
            ) as delete_pdf,
        ):
            winner = await _create_briefing_pdf(
                briefing_id,
                str(briefing_id),
                summary,
                admin_client,
            )
            with self.assertRaises(PDFBusyError):
                await _create_briefing_pdf(
                    briefing_id,
                    str(briefing_id),
                    summary,
                    admin_client,
                )

        winner_key = upload_pdf.await_args_list[0].kwargs["object_key"]
        stale_key = upload_pdf.await_args_list[1].kwargs["object_key"]
        self.assertNotEqual(winner_key, stale_key)
        self.assertIn(str(winner_token), winner_key)
        self.assertIn(str(stale_token), stale_key)
        self.assertEqual(winner.pdf_url, "https://storage.example/winner")
        self.assertEqual(
            complete_pdf.await_args_list[0].kwargs["pdf_object_key"],
            winner_key,
        )
        self.assertEqual(
            complete_pdf.await_args_list[1].kwargs["pdf_object_key"],
            stale_key,
        )
        delete_pdf.assert_awaited_once_with(
            admin_client,
            bucket=SUPABASE_PDF_BUCKET,
            object_key=stale_key,
        )

    async def test_failed_render_releases_the_database_claim(self) -> None:
        briefing_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        summary = {
            "id": str(briefing_id),
            "user_id": "user-123",
            "transcript_id": "transcript-123",
            "summary_markdown": "# Complete",
        }
        admin_client = object()

        with (
            patch(
                "fathom.application.briefings.prepare_summary_pdf",
                AsyncMock(
                    return_value=PdfPreparation(
                        resolution_type="acquired",
                        pdf_object_key=None,
                    )
                ),
            ),
            patch(
                "fathom.application.briefings.render_markdown_pdf_bytes",
                AsyncMock(side_effect=PDFError(PDF_RENDER_FAILED_MESSAGE)),
            ),
            patch(
                "fathom.application.briefings.fail_summary_pdf",
                AsyncMock(return_value=True),
            ) as fail_pdf,
        ):
            with self.assertRaises(PDFError):
                await _create_briefing_pdf(
                    briefing_id,
                    str(briefing_id),
                    summary,
                    admin_client,
                )

        fail_pdf.assert_awaited_once()

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

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fathom.api.deps.auth import AuthContext
from fathom.application.briefings.contract import NormalizedSource
from fathom.application.briefings.sessions import (
    _create_ready_reused_session,
    _fetch_summary_and_transcript_for_job,
    _find_ready_cached_summary,
    _job_has_ready_summary,
    create_briefing_session,
    delete_briefing_session,
)
from fathom.core.config import Settings
from fathom.core.errors import NotFoundError, UsageSettlementError
from fathom.crud.supabase.jobs import JobCreateResolution
from fathom.schemas.briefing_sessions import BriefingSessionCreateRequest
from fathom.schemas.transcripts import TranscriptSegment


class CreateBriefingSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_does_not_expose_summary_before_job_settlement_succeeds(self) -> None:
        with (
            patch(
                "fathom.application.briefings.sessions.fetch_summary",
                AsyncMock(),
            ) as fetch_summary_mock,
            patch(
                "fathom.application.briefings.sessions.fetch_transcript_by_id",
                AsyncMock(),
            ) as fetch_transcript_mock,
        ):
            summary, transcript = await _fetch_summary_and_transcript_for_job(
                object(),
                object(),
                {
                    "status": "running",
                    "stage": "finalizing",
                    "summary_id": "22222222-2222-2222-2222-222222222222",
                },
            )

        self.assertIsNone(summary)
        self.assertIsNone(transcript)
        fetch_summary_mock.assert_not_awaited()
        fetch_transcript_mock.assert_not_awaited()

    async def test_ready_cache_key_follows_transcript_evidence_availability(
        self,
    ) -> None:
        source = NormalizedSource(
            submitted_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            canonical_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            source_type="youtube",
            source_identity_key="youtube:dQw4w9WgXcQ",
            video_id="dQw4w9WgXcQ",
        )
        segment = TranscriptSegment(
            segment_index=0,
            start_seconds=0,
            end_seconds=10,
            text="Evidence.",
        )

        for segments, expected_prompt_key in (
            ((segment,), "briefing-v6-evidence-links"),
            ((), "briefing-v4"),
        ):
            with (
                patch(
                    "fathom.application.briefings.sessions.fetch_transcript_by_video_id",
                    AsyncMock(return_value={"id": "11111111-1111-1111-1111-111111111111"}),
                ),
                patch(
                    "fathom.application.briefings.sessions.fetch_transcript_segments",
                    AsyncMock(return_value=segments),
                ),
                patch(
                    "fathom.application.briefings.sessions.fetch_summary_by_keys",
                    AsyncMock(
                        return_value={
                            "id": "22222222-2222-2222-2222-222222222222",
                            "summary_markdown": "# Ready",
                        }
                    ),
                ) as fetch_summary,
            ):
                result = await _find_ready_cached_summary(object(), source)

            self.assertIsNotNone(result)
            self.assertEqual(
                fetch_summary.await_args.kwargs["prompt_key"],
                expected_prompt_key,
            )

    async def test_reusable_job_requires_explicit_ready_non_empty_summary(self) -> None:
        client = object()
        job = {
            "id": "11111111-1111-1111-1111-111111111111",
            "summary_id": "22222222-2222-2222-2222-222222222222",
        }

        with patch(
            "fathom.application.briefings.sessions.fetch_summary",
            AsyncMock(
                return_value={
                    "id": job["summary_id"],
                    "status": "failed",
                    "summary_markdown": "",
                }
            ),
        ):
            reusable = await _job_has_ready_summary(client, job)

        self.assertFalse(reusable)

    async def test_creates_job_with_atomic_server_command_after_user_scoped_lookup(self) -> None:
        auth = AuthContext(access_token="access-token", user_id="user-123")
        settings = cast(Settings, SimpleNamespace())
        request = BriefingSessionCreateRequest(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        user_client = object()
        admin_client = object()
        session_id = "11111111-1111-1111-1111-111111111111"
        expected_response = object()
        created_resolution = JobCreateResolution(
            job={"id": session_id},
            resolution_type="new",
        )

        with (
            patch(
                "fathom.application.briefings.sessions.create_supabase_user_client",
                AsyncMock(return_value=user_client),
            ),
            patch(
                "fathom.application.briefings.sessions.create_supabase_admin_client",
                AsyncMock(return_value=admin_client),
            ),
            patch(
                "fathom.application.briefings.sessions.fetch_active_job_for_source",
                AsyncMock(return_value=None),
            ) as fetch_active_job,
            patch(
                "fathom.application.briefings.sessions.fetch_reusable_job_for_source",
                AsyncMock(return_value=None),
            ) as fetch_reusable_job,
            patch(
                "fathom.application.briefings.sessions.fetch_video_metadata",
                return_value=SimpleNamespace(
                    video_id="dQw4w9WgXcQ",
                    duration_seconds=1800,
                    title="Example",
                ),
            ),
            patch("fathom.application.briefings.sessions.ensure_usage_allowed", AsyncMock()),
            patch(
                "fathom.application.briefings.sessions._find_ready_cached_summary",
                AsyncMock(return_value=None),
            ),
            patch(
                "fathom.application.briefings.sessions.create_or_reuse_job",
                AsyncMock(return_value=created_resolution),
            ) as create_job_mock,
            patch(
                "fathom.application.briefings.sessions.fetch_job",
                AsyncMock(return_value={"id": session_id, "status": "queued"}),
            ) as fetch_job_mock,
            patch("fathom.application.briefings.sessions.record_job_event_best_effort", AsyncMock()),
            patch(
                "fathom.application.briefings.sessions._build_session_snapshot",
                AsyncMock(return_value=expected_response),
            ),
        ):
            response = await create_briefing_session(request, auth, settings)

        self.assertIs(response, expected_response)
        fetch_active_job.assert_awaited_once_with(
            user_client,
            user_id=auth.user_id,
            source_key="youtube:dQw4w9WgXcQ",
        )
        fetch_reusable_job.assert_awaited_once_with(
            user_client,
            user_id=auth.user_id,
            source_key="youtube:dQw4w9WgXcQ",
        )
        create_job_mock.assert_awaited_once_with(
            admin_client,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            source_key="youtube:dQw4w9WgXcQ",
            user_id=auth.user_id,
            duration_seconds=1800,
        )
        fetch_job_mock.assert_awaited_once_with(user_client, session_id)

    async def test_restores_archived_job_with_admin_client_after_user_scoped_lookup(self) -> None:
        auth = AuthContext(access_token="access-token", user_id="user-123")
        settings = cast(Settings, SimpleNamespace())
        request = BriefingSessionCreateRequest(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        user_client = object()
        admin_client = object()
        session_id = "11111111-1111-1111-1111-111111111111"
        archived_job = {
            "id": session_id,
            "status": "deleted",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "summary_id": "22222222-2222-2222-2222-222222222222",
        }
        restored_job = {**archived_job, "status": "succeeded"}
        expected_response = object()

        with (
            patch(
                "fathom.application.briefings.sessions.create_supabase_user_client",
                AsyncMock(return_value=user_client),
            ),
            patch(
                "fathom.application.briefings.sessions.create_supabase_admin_client",
                AsyncMock(return_value=admin_client),
            ),
            patch(
                "fathom.application.briefings.sessions.fetch_active_job_for_source",
                AsyncMock(return_value=None),
            ),
            patch(
                "fathom.application.briefings.sessions.fetch_reusable_job_for_source",
                AsyncMock(return_value=archived_job),
            ),
            patch(
                "fathom.application.briefings.sessions.fetch_summary",
                AsyncMock(
                    return_value={
                        "id": "22222222-2222-2222-2222-222222222222",
                        "status": "ready",
                        "summary_markdown": "# Ready",
                    }
                ),
            ),
            patch("fathom.application.briefings.sessions.restore_job", AsyncMock()) as restore_job_mock,
            patch(
                "fathom.application.briefings.sessions.fetch_job",
                AsyncMock(return_value=restored_job),
            ) as fetch_job_mock,
            patch(
                "fathom.application.briefings.sessions._build_session_snapshot",
                AsyncMock(return_value=expected_response),
            ),
        ):
            response = await create_briefing_session(request, auth, settings)

        self.assertIs(response, expected_response)
        restore_job_mock.assert_awaited_once_with(admin_client, job_id=session_id)
        fetch_job_mock.assert_awaited_once_with(user_client, session_id)

    async def test_cached_session_job_uses_admin_client(self) -> None:
        settings = cast(Settings, SimpleNamespace())
        user_client = object()
        admin_client = object()
        session_id = "11111111-1111-1111-1111-111111111111"
        source = NormalizedSource(
            submitted_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            canonical_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            source_type="youtube",
            source_identity_key="youtube:dQw4w9WgXcQ",
            video_id="dQw4w9WgXcQ",
        )
        expected_job = {"id": session_id, "status": "succeeded"}

        with (
            patch(
                "fathom.application.briefings.sessions.create_or_reuse_job",
                AsyncMock(
                    return_value=JobCreateResolution(
                        job={
                            "id": session_id,
                            "lease_token": "33333333-3333-3333-3333-333333333333",
                        },
                        resolution_type="new",
                    )
                ),
            ) as create_job_mock,
            patch(
                "fathom.application.briefings.sessions.record_usage_for_job",
                AsyncMock(),
            ) as record_usage,
            patch(
                "fathom.application.briefings.sessions.mark_job_succeeded",
                AsyncMock(),
            ) as mark_succeeded,
            patch(
                "fathom.application.briefings.sessions.fetch_job",
                AsyncMock(return_value=expected_job),
            ) as fetch_job_mock,
        ):
            job = await _create_ready_reused_session(
                user_id="user-123",
                source=source,
                duration_seconds=1800,
                summary_id="22222222-2222-2222-2222-222222222222",
                user_client=user_client,
                admin_client=admin_client,
                settings=settings,
            )

        self.assertEqual(job.job, expected_job)
        self.assertEqual(job.resolution_type, "new")
        create_job_mock.assert_awaited_once_with(
            admin_client,
            url=source.canonical_url,
            source_key=source.source_identity_key,
            user_id="user-123",
            duration_seconds=1800,
            summary_id="22222222-2222-2222-2222-222222222222",
        )
        fetch_job_mock.assert_awaited_once_with(user_client, session_id)
        record_usage.assert_awaited_once_with(
            user_id="user-123",
            job_id=session_id,
            lease_token="33333333-3333-3333-3333-333333333333",
            duration_seconds=1800,
            settings=settings,
            admin_client=admin_client,
        )
        mark_succeeded.assert_awaited_once_with(
            admin_client,
            job_id=session_id,
            summary_id="22222222-2222-2222-2222-222222222222",
            lease_token="33333333-3333-3333-3333-333333333333",
        )

    async def test_cached_session_join_does_not_overwrite_or_charge_existing_job(self) -> None:
        settings = cast(Settings, SimpleNamespace())
        user_client = object()
        admin_client = object()
        session_id = "11111111-1111-1111-1111-111111111111"
        source = NormalizedSource(
            submitted_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            canonical_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            source_type="youtube",
            source_identity_key="youtube:dQw4w9WgXcQ",
            video_id="dQw4w9WgXcQ",
        )
        expected_job = {"id": session_id, "status": "running"}

        with (
            patch(
                "fathom.application.briefings.sessions.create_or_reuse_job",
                AsyncMock(
                    return_value=JobCreateResolution(
                        job={"id": session_id},
                        resolution_type="joined_existing",
                    )
                ),
            ),
            patch(
                "fathom.application.briefings.sessions.record_usage_for_job",
                AsyncMock(),
            ) as record_usage,
            patch(
                "fathom.application.briefings.sessions.fetch_job",
                AsyncMock(return_value=expected_job),
            ),
        ):
            resolution = await _create_ready_reused_session(
                user_id="user-123",
                source=source,
                duration_seconds=1800,
                summary_id="22222222-2222-2222-2222-222222222222",
                user_client=user_client,
                admin_client=admin_client,
                settings=settings,
            )

        self.assertEqual(resolution.job, expected_job)
        self.assertEqual(resolution.resolution_type, "joined_existing")
        record_usage.assert_not_awaited()

    async def test_cached_settlement_failure_returns_visible_finalization_retry(self) -> None:
        settings = cast(Settings, SimpleNamespace())
        user_client = object()
        admin_client = object()
        session_id = "11111111-1111-1111-1111-111111111111"
        lease_token = "33333333-3333-3333-3333-333333333333"
        summary_id = "22222222-2222-2222-2222-222222222222"
        source = NormalizedSource(
            submitted_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            canonical_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            source_type="youtube",
            source_identity_key="youtube:dQw4w9WgXcQ",
            video_id="dQw4w9WgXcQ",
        )
        expected_job = {
            "id": session_id,
            "status": "queued",
            "stage": "finalizing",
            "progress": 98,
        }
        settlement_error = UsageSettlementError("Usage accounting could not be finalized; retrying shortly.")

        with (
            patch(
                "fathom.application.briefings.sessions.create_or_reuse_job",
                AsyncMock(
                    return_value=JobCreateResolution(
                        job={"id": session_id, "lease_token": lease_token},
                        resolution_type="new",
                    )
                ),
            ),
            patch(
                "fathom.application.briefings.sessions.record_usage_for_job",
                AsyncMock(side_effect=settlement_error),
            ),
            patch(
                "fathom.application.briefings.sessions.mark_job_succeeded",
                AsyncMock(),
            ) as mark_succeeded,
            patch(
                "fathom.application.briefings.sessions.mark_job_finalization_retry",
                AsyncMock(),
            ) as mark_retry,
            patch(
                "fathom.application.briefings.sessions.fetch_job",
                AsyncMock(return_value=expected_job),
            ),
        ):
            resolution = await _create_ready_reused_session(
                user_id="user-123",
                source=source,
                duration_seconds=1800,
                summary_id=summary_id,
                user_client=user_client,
                admin_client=admin_client,
                settings=settings,
            )

        self.assertEqual(resolution.job, expected_job)
        mark_succeeded.assert_not_awaited()
        mark_retry.assert_awaited_once()
        retry_kwargs = mark_retry.await_args.kwargs
        self.assertEqual(retry_kwargs["job_id"], session_id)
        self.assertEqual(retry_kwargs["lease_token"], lease_token)
        self.assertEqual(retry_kwargs["error_code"], "usage_settlement_failed")


class DeleteBriefingSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_archives_ready_session_with_admin_client_after_ownership_check(self) -> None:
        auth = AuthContext(access_token="access-token", user_id="user-123")
        settings = cast(Settings, SimpleNamespace())
        session_id = UUID("11111111-1111-1111-1111-111111111111")
        user_client = object()
        admin_client = object()

        with (
            patch(
                "fathom.application.briefings.sessions.create_supabase_user_client",
                AsyncMock(return_value=user_client),
            ) as create_user_client,
            patch(
                "fathom.application.briefings.sessions.create_supabase_admin_client",
                AsyncMock(return_value=admin_client),
            ) as create_admin_client,
            patch(
                "fathom.application.briefings.sessions.fetch_job",
                AsyncMock(
                    return_value={
                        "id": str(session_id),
                        "status": "succeeded",
                        "summary_id": "22222222-2222-2222-2222-222222222222",
                    }
                ),
            ) as fetch_job_mock,
            patch("fathom.application.briefings.sessions.archive_job", AsyncMock()) as archive_job_mock,
        ):
            await delete_briefing_session(session_id, auth, settings)

        create_user_client.assert_awaited_once_with(settings, auth.access_token)
        fetch_job_mock.assert_awaited_once_with(user_client, str(session_id))
        create_admin_client.assert_awaited_once_with(settings)
        archive_job_mock.assert_awaited_once_with(admin_client, job_id=str(session_id))

    async def test_rejects_session_without_briefing(self) -> None:
        auth = AuthContext(access_token="access-token", user_id="user-123")
        settings = cast(Settings, SimpleNamespace())
        session_id = UUID("11111111-1111-1111-1111-111111111111")
        user_client = object()

        with (
            patch(
                "fathom.application.briefings.sessions.create_supabase_user_client",
                AsyncMock(return_value=user_client),
            ),
            patch(
                "fathom.application.briefings.sessions.fetch_job",
                AsyncMock(
                    return_value={
                        "id": str(session_id),
                        "status": "queued",
                        "summary_id": None,
                    }
                ),
            ),
            patch(
                "fathom.application.briefings.sessions.create_supabase_admin_client",
                AsyncMock(),
            ) as create_admin_client,
            patch("fathom.application.briefings.sessions.archive_job", AsyncMock()) as archive_job_mock,
        ):
            with self.assertRaises(NotFoundError):
                await delete_briefing_session(session_id, auth, settings)

        create_admin_client.assert_not_awaited()
        archive_job_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

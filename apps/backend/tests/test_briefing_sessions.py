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
    create_briefing_session,
    delete_briefing_session,
)
from fathom.core.config import Settings
from fathom.core.errors import NotFoundError
from fathom.schemas.briefing_sessions import BriefingSessionCreateRequest


class CreateBriefingSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_creates_job_with_admin_client_after_user_scoped_lookup(self) -> None:
        auth = AuthContext(access_token="access-token", user_id="user-123")
        settings = cast(Settings, SimpleNamespace())
        request = BriefingSessionCreateRequest(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        user_client = object()
        admin_client = object()
        session_id = "11111111-1111-1111-1111-111111111111"
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
                "fathom.application.briefings.sessions.create_job",
                AsyncMock(return_value={"id": session_id}),
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
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        fetch_reusable_job.assert_awaited_once_with(
            user_client,
            user_id=auth.user_id,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        create_job_mock.assert_awaited_once_with(
            admin_client,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
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
                "fathom.application.briefings.sessions.create_job",
                AsyncMock(return_value={"id": session_id}),
            ) as create_job_mock,
            patch("fathom.application.briefings.sessions.update_job_progress", AsyncMock()),
            patch("fathom.application.briefings.sessions.mark_job_succeeded", AsyncMock()),
            patch("fathom.application.briefings.sessions.record_usage_for_job", AsyncMock()),
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

        self.assertEqual(job, expected_job)
        create_job_mock.assert_awaited_once_with(
            admin_client,
            url=source.canonical_url,
            user_id="user-123",
            duration_seconds=1800,
        )
        fetch_job_mock.assert_awaited_once_with(user_client, session_id)


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

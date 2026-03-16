from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fathom.api.deps.auth import AuthContext
from fathom.application.briefing_sessions import delete_briefing_session
from fathom.core.config import Settings
from fathom.core.errors import NotFoundError


class DeleteBriefingSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_archives_ready_session_with_admin_client_after_ownership_check(self) -> None:
        auth = AuthContext(access_token="access-token", user_id="user-123")
        settings = cast(Settings, SimpleNamespace())
        session_id = UUID("11111111-1111-1111-1111-111111111111")
        user_client = object()
        admin_client = object()

        with (
            patch(
                "fathom.application.briefing_sessions.create_supabase_user_client",
                AsyncMock(return_value=user_client),
            ) as create_user_client,
            patch(
                "fathom.application.briefing_sessions.create_supabase_admin_client",
                AsyncMock(return_value=admin_client),
            ) as create_admin_client,
            patch(
                "fathom.application.briefing_sessions.fetch_job",
                AsyncMock(
                    return_value={
                        "id": str(session_id),
                        "status": "succeeded",
                        "summary_id": "22222222-2222-2222-2222-222222222222",
                    }
                ),
            ) as fetch_job_mock,
            patch("fathom.application.briefing_sessions.archive_job", AsyncMock()) as archive_job_mock,
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
                "fathom.application.briefing_sessions.create_supabase_user_client",
                AsyncMock(return_value=user_client),
            ),
            patch(
                "fathom.application.briefing_sessions.fetch_job",
                AsyncMock(
                    return_value={
                        "id": str(session_id),
                        "status": "queued",
                        "summary_id": None,
                    }
                ),
            ),
            patch(
                "fathom.application.briefing_sessions.create_supabase_admin_client",
                AsyncMock(),
            ) as create_admin_client,
            patch("fathom.application.briefing_sessions.archive_job", AsyncMock()) as archive_job_mock,
        ):
            with self.assertRaises(NotFoundError):
                await delete_briefing_session(session_id, auth, settings)

        create_admin_client.assert_not_awaited()
        archive_job_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

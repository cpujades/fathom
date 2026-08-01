from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import UUID

from starlette.requests import Request

from fathom.api.deps.auth import AuthContext
from fathom.application.briefings.sessions import _session_event_stream, stream_briefing_session_events
from fathom.core.config import Settings
from fathom.core.errors import RateLimitError
from fathom.schemas.briefing_sessions import BriefingSessionResponse

SESSION_ID = UUID("11111111-1111-1111-1111-111111111111")


def _snapshot(*, state: str, markdown: str | None = None) -> BriefingSessionResponse:
    return BriefingSessionResponse.model_validate(
        {
            "session_id": str(SESSION_ID),
            "briefing_id": "22222222-2222-2222-2222-222222222222" if markdown else None,
            "state": state,
            "message": "Your briefing is ready" if state == "ready" else "Working",
            "progress": 100 if state in {"ready", "failed"} else 30,
            "resolution_type": "new",
            "submitted_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "canonical_source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "source_type": "youtube",
            "source_identity_key": "youtube:dQw4w9WgXcQ",
            "source_title": "Example",
            "session_url": f"/briefing-sessions/{SESSION_ID}",
            "events_url": f"/briefing-sessions/{SESSION_ID}/events",
            "briefing_markdown": markdown,
        }
    )


class SessionEventStreamTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.auth = AuthContext(access_token="access-token", user_id="user-1")
        self.settings = cast(
            Settings,
            SimpleNamespace(
                sse_stream_lease_seconds=90,
                sse_stream_max_lifetime_seconds=3600,
            ),
        )
        self.user_client = object()
        self.admin_client = object()

    async def test_stream_capacity_is_rejected_before_response_starts(self) -> None:
        settings = cast(
            Settings,
            SimpleNamespace(
                sse_max_streams_per_user=3,
                sse_max_streams_per_ip=12,
                sse_stream_lease_seconds=90,
            ),
        )
        request = cast(
            Request,
            SimpleNamespace(
                app=SimpleNamespace(
                    state=SimpleNamespace(
                        trust_proxy_headers=False,
                        trusted_proxy_networks=(),
                    )
                ),
                client=SimpleNamespace(host="203.0.113.4"),
                headers={},
            ),
        )

        with (
            patch(
                "fathom.application.briefings.sessions.create_supabase_admin_client",
                AsyncMock(return_value=self.admin_client),
            ),
            patch(
                "fathom.application.briefings.sessions.claim_stream_lease",
                AsyncMock(return_value=None),
            ) as claim,
            self.assertRaisesRegex(RateLimitError, "Too many active briefing streams"),
        ):
            await stream_briefing_session_events(
                session_id=SESSION_ID,
                auth=self.auth,
                settings=settings,
                request=request,
            )

        claim.assert_awaited_once_with(
            self.admin_client,
            user_id="user-1",
            client_subject="ip:203.0.113.4",
            max_per_user=3,
            max_per_subject=12,
            lease_seconds=90,
        )

    async def test_reconnect_replays_stable_ids_before_snapshot(self) -> None:
        request = SimpleNamespace(
            headers={"last-event-id": "8"},
            is_disconnected=AsyncMock(return_value=True),
        )
        job = {
            "id": str(SESSION_ID),
            "status": "running",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        }
        replay = [
            {
                "sequence_id": 9,
                "event_type": "job_state_changed",
                "stage": "transcribing",
                "created_at": "2026-07-29T12:00:00Z",
            },
            {
                "sequence_id": 10,
                "event_type": "transcript_completed",
                "stage": "transcribing",
                "created_at": "2026-07-29T12:01:00Z",
            },
        ]

        with (
            patch(
                "fathom.application.briefings.sessions.create_supabase_user_client",
                AsyncMock(return_value=self.user_client),
            ),
            patch(
                "fathom.application.briefings.sessions.create_supabase_admin_client",
                AsyncMock(return_value=self.admin_client),
            ),
            patch("fathom.application.briefings.sessions.fetch_job", AsyncMock(return_value=job)),
            patch(
                "fathom.application.briefings.sessions.fetch_latest_job_event_sequence",
                AsyncMock(return_value=10),
            ),
            patch(
                "fathom.application.briefings.sessions.list_job_events_after",
                AsyncMock(return_value=replay),
            ) as list_after,
            patch(
                "fathom.application.briefings.sessions._build_session_snapshot",
                AsyncMock(return_value=_snapshot(state="transcribing")),
            ),
        ):
            chunks = [
                chunk
                async for chunk in _session_event_stream(
                    session_id=SESSION_ID,
                    auth=self.auth,
                    settings=self.settings,
                    request=cast(Request, request),
                )
            ]

        self.assertIn("id: 9\nevent: session.event", chunks[1])
        self.assertIn("id: 10\nevent: session.event", chunks[2])
        self.assertIn("id: 10\nevent: session.snapshot", chunks[3])
        list_after.assert_awaited_once_with(
            self.user_client,
            job_id=str(SESSION_ID),
            after_sequence_id=8,
            limit=100,
        )

    async def test_disconnect_stops_before_polling(self) -> None:
        request = SimpleNamespace(headers={}, is_disconnected=AsyncMock(return_value=True))
        job = {
            "id": str(SESSION_ID),
            "status": "running",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        }

        with (
            patch(
                "fathom.application.briefings.sessions.create_supabase_user_client",
                AsyncMock(return_value=self.user_client),
            ),
            patch(
                "fathom.application.briefings.sessions.create_supabase_admin_client",
                AsyncMock(return_value=self.admin_client),
            ),
            patch("fathom.application.briefings.sessions.fetch_job", AsyncMock(return_value=job)),
            patch(
                "fathom.application.briefings.sessions.fetch_latest_job_event_sequence",
                AsyncMock(return_value=37),
            ),
            patch(
                "fathom.application.briefings.sessions.list_job_events_after",
                AsyncMock(),
            ) as list_after,
            patch(
                "fathom.application.briefings.sessions._build_session_snapshot",
                AsyncMock(return_value=_snapshot(state="transcribing")),
            ),
        ):
            chunks = [
                chunk
                async for chunk in _session_event_stream(
                    session_id=SESSION_ID,
                    auth=self.auth,
                    settings=self.settings,
                    request=cast(Request, request),
                )
            ]

        self.assertIn("id: 37\nevent: session.snapshot", chunks[1])
        list_after.assert_not_awaited()

    async def test_terminal_transition_includes_complete_content(self) -> None:
        request = SimpleNamespace(headers={}, is_disconnected=AsyncMock(return_value=False))
        active_job = {
            "id": str(SESSION_ID),
            "status": "running",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        }
        ready_job = {**active_job, "status": "succeeded"}
        final_markdown = "# Briefing\n\nFinal evidence-backed content."

        with (
            patch(
                "fathom.application.briefings.sessions.create_supabase_user_client",
                AsyncMock(return_value=self.user_client),
            ),
            patch(
                "fathom.application.briefings.sessions.create_supabase_admin_client",
                AsyncMock(return_value=self.admin_client),
            ),
            patch(
                "fathom.application.briefings.sessions.fetch_job",
                AsyncMock(side_effect=[active_job, ready_job]),
            ),
            patch(
                "fathom.application.briefings.sessions.fetch_latest_job_event_sequence",
                AsyncMock(side_effect=[40, 41]),
            ),
            patch(
                "fathom.application.briefings.sessions.list_job_events_after",
                AsyncMock(
                    return_value=[
                        {
                            "sequence_id": 41,
                            "event_type": "job_state_changed",
                            "stage": "completed",
                            "created_at": "2026-07-29T12:02:00Z",
                        }
                    ]
                ),
            ),
            patch(
                "fathom.application.briefings.sessions._build_session_snapshot",
                AsyncMock(
                    side_effect=[
                        _snapshot(state="transcribing"),
                        _snapshot(state="ready", markdown=final_markdown),
                    ]
                ),
            ),
            patch("fathom.application.briefings.sessions.asyncio.sleep", AsyncMock()),
        ):
            chunks = [
                chunk
                async for chunk in _session_event_stream(
                    session_id=SESSION_ID,
                    auth=self.auth,
                    settings=self.settings,
                    request=cast(Request, request),
                )
            ]

        terminal_chunks = "\n".join(chunks)
        self.assertIn("id: 41\nevent: session.content_delta", terminal_chunks)
        self.assertIn("id: 41\nevent: session.snapshot", terminal_chunks)
        self.assertIn("Final evidence-backed content.", terminal_chunks)

    async def test_terminal_reconnect_returns_snapshot_with_existing_cursor(self) -> None:
        request = SimpleNamespace(
            headers={"last-event-id": "52"},
            is_disconnected=AsyncMock(return_value=False),
        )
        ready_job = {
            "id": str(SESSION_ID),
            "status": "succeeded",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        }

        with (
            patch(
                "fathom.application.briefings.sessions.create_supabase_user_client",
                AsyncMock(return_value=self.user_client),
            ),
            patch(
                "fathom.application.briefings.sessions.create_supabase_admin_client",
                AsyncMock(return_value=self.admin_client),
            ),
            patch("fathom.application.briefings.sessions.fetch_job", AsyncMock(return_value=ready_job)),
            patch(
                "fathom.application.briefings.sessions.fetch_latest_job_event_sequence",
                AsyncMock(return_value=52),
            ),
            patch(
                "fathom.application.briefings.sessions.list_job_events_after",
                AsyncMock(),
            ) as list_after,
            patch(
                "fathom.application.briefings.sessions._build_session_snapshot",
                AsyncMock(return_value=_snapshot(state="ready", markdown="# Complete")),
            ),
        ):
            chunks = [
                chunk
                async for chunk in _session_event_stream(
                    session_id=SESSION_ID,
                    auth=self.auth,
                    settings=self.settings,
                    request=cast(Request, request),
                )
            ]

        self.assertIn("id: 52\nevent: session.snapshot", chunks[1])
        self.assertIn("# Complete", chunks[1])
        list_after.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

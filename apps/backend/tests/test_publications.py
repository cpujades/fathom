from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from postgrest import APIError

from fathom.api.routers.publications import router as publications_router
from fathom.application.identity import AuthenticatedUser
from fathom.application.publications import (
    _uses_current_generation_contract,
    find_listed_publication_for_source,
    get_public_briefing,
    get_publication_library_entries,
    get_publication_library_entry,
    list_explore_briefings,
    match_listed_publication,
    save_public_briefing,
    set_owner_publication,
)
from fathom.core.config import Settings, get_settings
from fathom.core.constants import GROQ_TRANSCRIPT_PROVIDER_MODEL, SUMMARY_PROMPT_KEY_EVIDENCE
from fathom.core.errors import ConflictError, ForbiddenError
from fathom.crud.supabase.publications import create_publication
from fathom.schemas.publications import (
    ExploreBriefingItem,
    ExploreTopic,
    PublicationLibraryEntriesRequest,
    PublicationLibraryEntryResponse,
    PublicationUpdateRequest,
)
from fathom.services.summarizer import OPENROUTER_MODEL

SESSION_ID = UUID("11111111-1111-1111-1111-111111111111")
SUMMARY_ID = "22222222-2222-2222-2222-222222222222"
SLUG = "a" * 32


def _settings(*, operators: tuple[str, ...] = ()) -> Settings:
    return cast(Settings, SimpleNamespace(explore_operator_user_ids=operators))


class PublicationTests(unittest.IsolatedAsyncioTestCase):
    def test_topics_are_controlled_and_public_slugs_are_bounded(self) -> None:
        request = PublicationLibraryEntriesRequest(public_slugs=[SLUG, SLUG])

        self.assertEqual(request.public_slugs, [SLUG])
        self.assertIn(ExploreTopic.PRODUCTIVITY, list(ExploreTopic))
        with self.assertRaises(ValueError):
            PublicationUpdateRequest(visibility="listed", topic="anything")
        with self.assertRaises(ValueError):
            PublicationLibraryEntriesRequest(public_slugs=["not-a-slug"])

    async def test_explore_rejects_an_unknown_topic(self) -> None:
        app = FastAPI()
        app.include_router(publications_router)
        app.dependency_overrides[get_settings] = _settings

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
            response = await client.get("/explore", params={"topic": "anything"})

        self.assertEqual(response.status_code, 422)

    def test_current_generation_contract_requires_all_three_cache_keys(self) -> None:
        summary = {
            "prompt_key": SUMMARY_PROMPT_KEY_EVIDENCE,
            "summary_model": OPENROUTER_MODEL,
        }
        transcript = {"provider_model": GROQ_TRANSCRIPT_PROVIDER_MODEL}

        self.assertTrue(_uses_current_generation_contract(summary, transcript))
        self.assertFalse(_uses_current_generation_contract({**summary, "prompt_key": "old"}, transcript))
        self.assertFalse(_uses_current_generation_contract(summary, {"provider_model": "old"}))

    async def test_owner_can_publish_completed_briefing_as_unlisted(self) -> None:
        auth = AuthenticatedUser(access_token="token", user_id="user-123")
        user_client = object()
        admin_client = object()
        publication = {
            "id": "33333333-3333-3333-3333-333333333333",
            "public_slug": SLUG,
            "visibility": "unlisted",
            "topic": None,
            "published_at": "2026-08-12T08:00:00+00:00",
            "listed_at": None,
        }

        with (
            patch(
                "fathom.application.publications.create_supabase_user_client",
                AsyncMock(return_value=user_client),
            ),
            patch(
                "fathom.application.publications.create_supabase_admin_client",
                AsyncMock(return_value=admin_client),
            ),
            patch(
                "fathom.application.publications.fetch_job",
                AsyncMock(return_value={"id": str(SESSION_ID), "status": "succeeded", "summary_id": SUMMARY_ID}),
            ),
            patch(
                "fathom.application.publications.fetch_owner_publication",
                AsyncMock(return_value=None),
            ),
            patch(
                "fathom.application.publications.create_publication",
                AsyncMock(return_value=publication),
            ) as create_publication,
        ):
            response = await set_owner_publication(
                SESSION_ID,
                PublicationUpdateRequest(visibility="unlisted"),
                auth,
                _settings(),
            )

        create_publication.assert_awaited_once_with(
            admin_client,
            owner_user_id=auth.user_id,
            owner_job_id=str(SESSION_ID),
            summary_id=SUMMARY_ID,
            visibility="unlisted",
            topic=None,
        )
        self.assertEqual(response.public_path, f"/b/{SLUG}")
        self.assertEqual(response.visibility, "unlisted")
        self.assertFalse(response.can_list)
        self.assertIn(ExploreTopic.BUSINESS, response.available_topics)

    async def test_first_publication_write_uses_an_atomic_owner_job_upsert(self) -> None:
        client = MagicMock()
        query = MagicMock()
        client.table.return_value = query
        query.upsert.return_value = query
        query.execute = AsyncMock(
            return_value=SimpleNamespace(
                data=[
                    {
                        "public_slug": SLUG,
                        "visibility": "unlisted",
                    }
                ]
            )
        )

        response = await create_publication(
            client,
            owner_user_id="user-123",
            owner_job_id=str(SESSION_ID),
            summary_id=SUMMARY_ID,
            visibility="unlisted",
            topic=None,
        )

        _, kwargs = query.upsert.call_args
        self.assertEqual(kwargs["on_conflict"], "owner_job_id")
        self.assertFalse(kwargs["default_to_null"])
        self.assertEqual(response["public_slug"], SLUG)

    async def test_duplicate_listed_source_returns_a_conflict(self) -> None:
        client = MagicMock()
        query = MagicMock()
        client.table.return_value = query
        query.upsert.return_value = query
        query.execute = AsyncMock(
            side_effect=APIError(
                {
                    "message": "duplicate key value violates unique constraint",
                    "code": "23505",
                    "hint": None,
                    "details": "Source already listed.",
                }
            )
        )

        with self.assertRaisesRegex(ConflictError, "already in Explore"):
            await create_publication(
                client,
                owner_user_id="user-123",
                owner_job_id=str(SESSION_ID),
                summary_id=SUMMARY_ID,
                visibility="listed",
                topic="business",
            )

    async def test_only_configured_operator_can_list_owned_briefing(self) -> None:
        auth = AuthenticatedUser(access_token="token", user_id="user-123")
        with (
            patch(
                "fathom.application.publications.create_supabase_user_client",
                AsyncMock(return_value=object()),
            ),
            patch(
                "fathom.application.publications.create_supabase_admin_client",
                AsyncMock(return_value=object()),
            ),
            patch(
                "fathom.application.publications.fetch_job",
                AsyncMock(return_value={"id": str(SESSION_ID), "status": "succeeded", "summary_id": SUMMARY_ID}),
            ),
            patch(
                "fathom.application.publications.fetch_owner_publication",
                AsyncMock(return_value=None),
            ),
            patch(
                "fathom.application.publications.create_publication",
                AsyncMock(),
            ) as create_publication,
        ):
            with self.assertRaises(ForbiddenError):
                await set_owner_publication(
                    SESSION_ID,
                    PublicationUpdateRequest(visibility="listed", topic="business"),
                    auth,
                    _settings(),
                )

        create_publication.assert_not_awaited()

    async def test_configured_operator_can_list_owned_briefing(self) -> None:
        auth = AuthenticatedUser(access_token="token", user_id="user-123")
        publication = {
            "public_slug": SLUG,
            "visibility": "listed",
            "topic": "business",
            "published_at": "2026-08-12T08:00:00+00:00",
            "listed_at": "2026-08-12T08:00:00+00:00",
        }
        with (
            patch(
                "fathom.application.publications.create_supabase_user_client",
                AsyncMock(return_value=object()),
            ),
            patch(
                "fathom.application.publications.create_supabase_admin_client",
                AsyncMock(return_value=object()),
            ),
            patch(
                "fathom.application.publications.fetch_job",
                AsyncMock(return_value={"id": str(SESSION_ID), "status": "succeeded", "summary_id": SUMMARY_ID}),
            ),
            patch(
                "fathom.application.publications.fetch_owner_publication",
                AsyncMock(return_value=None),
            ),
            patch(
                "fathom.application.publications.create_publication",
                AsyncMock(return_value=publication),
            ) as create_publication,
        ):
            response = await set_owner_publication(
                SESSION_ID,
                PublicationUpdateRequest(visibility="listed", topic="business"),
                auth,
                _settings(operators=(auth.user_id,)),
            )

        create_publication.assert_awaited_once()
        self.assertTrue(response.can_list)
        self.assertEqual(response.visibility, "listed")

    async def test_explore_page_hydrates_all_cards_with_batched_queries(self) -> None:
        transcript_id = "44444444-4444-4444-4444-444444444444"
        publication = {
            "owner_job_id": str(SESSION_ID),
            "summary_id": SUMMARY_ID,
            "public_slug": SLUG,
            "visibility": "listed",
            "topic": "business",
            "listed_at": "2026-08-12T08:00:00+00:00",
        }
        with (
            patch(
                "fathom.application.publications.create_supabase_admin_client",
                AsyncMock(return_value=object()),
            ),
            patch(
                "fathom.application.publications.fetch_listed_publications_page",
                AsyncMock(return_value=([publication], 1)),
            ),
            patch(
                "fathom.application.publications.fetch_jobs_by_ids",
                AsyncMock(
                    return_value=[
                        {
                            "id": str(SESSION_ID),
                            "status": "succeeded",
                            "summary_id": SUMMARY_ID,
                            "url": "https://www.youtube.com/watch?v=example",
                            "duration_seconds": 1800,
                        }
                    ]
                ),
            ) as fetch_jobs,
            patch(
                "fathom.application.publications.fetch_summaries_by_ids",
                AsyncMock(return_value=[{"id": SUMMARY_ID, "status": "ready", "transcript_id": transcript_id}]),
            ) as fetch_summaries,
            patch(
                "fathom.application.publications.fetch_transcripts_by_ids",
                AsyncMock(
                    return_value=[
                        {
                            "id": transcript_id,
                            "video_id": "example",
                            "source_title": "A serious conversation",
                        }
                    ]
                ),
            ) as fetch_transcripts,
            patch(
                "fathom.application.publications.fetch_publication_job",
                AsyncMock(),
            ) as fetch_one_job,
            patch(
                "fathom.application.publications.fetch_summary",
                AsyncMock(),
            ) as fetch_one_summary,
        ):
            response = await list_explore_briefings(
                settings=_settings(),
                limit=48,
                offset=0,
                topic=None,
            )

        self.assertEqual([item.title for item in response.items], ["A serious conversation"])
        fetch_jobs.assert_awaited_once_with(ANY, [str(SESSION_ID)])
        fetch_summaries.assert_awaited_once_with(ANY, [SUMMARY_ID])
        fetch_transcripts.assert_awaited_once_with(ANY, [transcript_id])
        fetch_one_job.assert_not_awaited()
        fetch_one_summary.assert_not_awaited()

    async def test_source_match_ignores_an_outdated_generation_contract(self) -> None:
        transcript_id = "44444444-4444-4444-4444-444444444444"
        publication = {
            "owner_job_id": str(SESSION_ID),
            "summary_id": SUMMARY_ID,
            "public_slug": SLUG,
            "visibility": "listed",
            "topic": "business",
            "listed_at": "2026-08-12T08:00:00+00:00",
        }
        with (
            patch(
                "fathom.application.publications.fetch_listed_publication_for_source",
                AsyncMock(return_value=publication),
            ),
            patch(
                "fathom.application.publications.fetch_publication_job",
                AsyncMock(
                    return_value={
                        "status": "succeeded",
                        "summary_id": SUMMARY_ID,
                        "url": "https://www.youtube.com/watch?v=example",
                    }
                ),
            ),
            patch(
                "fathom.application.publications.fetch_summary",
                AsyncMock(
                    return_value={
                        "id": SUMMARY_ID,
                        "status": "ready",
                        "summary_markdown": "# Briefing",
                        "transcript_id": transcript_id,
                        "prompt_key": "old-prompt",
                        "summary_model": "old-model",
                    }
                ),
            ),
            patch(
                "fathom.application.publications.fetch_transcript_by_id",
                AsyncMock(
                    return_value={
                        "id": transcript_id,
                        "provider_model": "old-transcript-model",
                        "video_id": "example",
                    }
                ),
            ),
        ):
            response = await find_listed_publication_for_source(object(), source_key="youtube:example")

        self.assertIsNone(response)

    async def test_source_match_includes_the_current_library_entry(self) -> None:
        auth = AuthenticatedUser(access_token="token", user_id="user-123")
        user_client = object()
        admin_client = object()
        match = ExploreBriefingItem(
            public_slug=SLUG,
            public_path=f"/b/{SLUG}",
            topic="business",
            title="A serious conversation",
            source_url="https://www.youtube.com/watch?v=example",
            source_type="youtube",
            listed_at="2026-08-12T08:00:00+00:00",
        )
        library_entry = PublicationLibraryEntryResponse(
            state="saved",
            session_id=SESSION_ID,
            session_path=f"/app/briefings/sessions/{SESSION_ID}",
        )

        with (
            patch(
                "fathom.application.publications.create_supabase_user_client",
                AsyncMock(return_value=user_client),
            ),
            patch(
                "fathom.application.publications.create_supabase_admin_client",
                AsyncMock(return_value=admin_client),
            ),
            patch(
                "fathom.application.publications.find_listed_publication_for_source",
                AsyncMock(return_value=match),
            ),
            patch(
                "fathom.application.publications._find_library_entry",
                AsyncMock(return_value=library_entry),
            ) as find_library_entry,
        ):
            response = await match_listed_publication(
                "https://www.youtube.com/watch?v=example",
                auth,
                _settings(),
            )

        self.assertEqual(response.match, match)
        self.assertEqual(response.library_entry, library_entry)
        find_library_entry.assert_awaited_once_with(
            user_client,
            user_id=auth.user_id,
            source_key="youtube:example",
        )

    async def test_explore_library_state_is_loaded_in_bounded_batches(self) -> None:
        auth = AuthenticatedUser(access_token="token", user_id="user-123")
        public_slugs = ["a" * 32, "b" * 32, "c" * 32]
        publications = [
            {"public_slug": public_slugs[0], "source_key": "youtube:saved"},
            {"public_slug": public_slugs[1], "source_key": "youtube:active"},
            {"public_slug": public_slugs[2], "source_key": "youtube:archived"},
        ]
        jobs = [
            {"id": "50000000-0000-0000-0000-000000000001", "source_key": "youtube:saved", "status": "succeeded"},
            {"id": "50000000-0000-0000-0000-000000000002", "source_key": "youtube:active", "status": "running"},
            {"id": "50000000-0000-0000-0000-000000000003", "source_key": "youtube:archived", "status": "deleted"},
            {"id": "50000000-0000-0000-0000-000000000004", "source_key": "youtube:archived", "status": "succeeded"},
        ]

        with (
            patch(
                "fathom.application.publications.create_supabase_user_client",
                AsyncMock(return_value=object()),
            ),
            patch(
                "fathom.application.publications.create_supabase_admin_client",
                AsyncMock(return_value=object()),
            ),
            patch(
                "fathom.application.publications.fetch_public_publications_by_slugs",
                AsyncMock(return_value=publications),
            ) as fetch_publications,
            patch(
                "fathom.application.publications.fetch_library_jobs_for_sources",
                AsyncMock(return_value=jobs),
            ) as fetch_jobs,
        ):
            response = await get_publication_library_entries(public_slugs, auth, _settings())

        fetch_publications.assert_awaited_once_with(ANY, public_slugs=public_slugs)
        fetch_jobs.assert_awaited_once_with(
            ANY,
            user_id=auth.user_id,
            source_keys=["youtube:saved", "youtube:active", "youtube:archived"],
        )
        self.assertEqual(response.entries[public_slugs[0]].state, "saved")
        self.assertEqual(response.entries[public_slugs[1]].state, "processing")
        self.assertEqual(response.entries[public_slugs[2]].state, "not_saved")

    async def test_public_read_returns_only_safe_presentation_fields(self) -> None:
        publication = {
            "owner_job_id": str(SESSION_ID),
            "summary_id": SUMMARY_ID,
            "public_slug": SLUG,
            "visibility": "unlisted",
            "topic": None,
            "published_at": "2026-08-12T08:00:00+00:00",
            "listed_at": None,
        }
        with (
            patch(
                "fathom.application.publications.create_supabase_admin_client",
                AsyncMock(return_value=object()),
            ),
            patch(
                "fathom.application.publications.fetch_public_publication",
                AsyncMock(return_value=publication),
            ),
            patch(
                "fathom.application.publications.fetch_publication_job",
                AsyncMock(
                    return_value={
                        "id": str(SESSION_ID),
                        "status": "succeeded",
                        "url": "https://www.youtube.com/watch?v=example",
                        "summary_id": SUMMARY_ID,
                        "duration_seconds": 1800,
                    }
                ),
            ),
            patch(
                "fathom.application.publications.fetch_summary",
                AsyncMock(
                    return_value={
                        "id": SUMMARY_ID,
                        "status": "ready",
                        "summary_markdown": "# Public briefing",
                        "transcript_id": "44444444-4444-4444-4444-444444444444",
                    }
                ),
            ),
            patch(
                "fathom.application.publications.fetch_transcript_by_id",
                AsyncMock(
                    return_value={
                        "video_id": "example",
                        "source_title": "A serious conversation",
                        "source_author": "Example Channel",
                        "source_length_seconds": 1750,
                    }
                ),
            ),
        ):
            response = await get_public_briefing(SLUG, _settings())

        self.assertEqual(response.title, "A serious conversation")
        self.assertEqual(response.markdown, "# Public briefing")
        self.assertEqual(response.public_path, f"/b/{SLUG}")
        self.assertNotIn("owner_user_id", response.model_dump())
        self.assertNotIn("summary_id", response.model_dump())

    async def test_save_uses_atomic_free_library_command(self) -> None:
        auth = AuthenticatedUser(access_token="token", user_id="user-123")
        job_id = "55555555-5555-5555-5555-555555555555"
        admin_client = object()
        with (
            patch(
                "fathom.application.publications.create_supabase_admin_client",
                AsyncMock(return_value=admin_client),
            ),
            patch(
                "fathom.application.publications.fetch_public_publication",
                AsyncMock(return_value={"public_slug": SLUG}),
            ),
            patch(
                "fathom.application.publications.save_publication",
                AsyncMock(return_value={"job": {"id": job_id, "status": "succeeded"}}),
            ) as save_publication,
        ):
            response = await save_public_briefing(SLUG, auth, _settings())

        save_publication.assert_awaited_once_with(
            admin_client,
            user_id=auth.user_id,
            public_slug=SLUG,
        )
        self.assertEqual(response.state, "saved")
        self.assertEqual(response.session_path, f"/app/briefings/sessions/{job_id}")

    async def test_archived_library_entry_is_not_reported_as_saved(self) -> None:
        auth = AuthenticatedUser(access_token="token", user_id="user-123")
        with (
            patch(
                "fathom.application.publications.create_supabase_user_client",
                AsyncMock(return_value=object()),
            ),
            patch(
                "fathom.application.publications.create_supabase_admin_client",
                AsyncMock(return_value=object()),
            ),
            patch(
                "fathom.application.publications.fetch_public_publication",
                AsyncMock(return_value={"owner_job_id": str(SESSION_ID)}),
            ),
            patch(
                "fathom.application.publications.fetch_publication_job",
                AsyncMock(return_value={"source_key": "youtube:example"}),
            ),
            patch(
                "fathom.application.publications.fetch_active_job_for_source",
                AsyncMock(return_value=None),
            ),
            patch(
                "fathom.application.publications.fetch_reusable_job_for_source",
                AsyncMock(return_value={"id": "archived", "status": "deleted"}),
            ),
        ):
            response = await get_publication_library_entry(SLUG, auth, _settings())

        self.assertEqual(response.state, "not_saved")
        self.assertIsNone(response.session_id)


if __name__ == "__main__":
    unittest.main()

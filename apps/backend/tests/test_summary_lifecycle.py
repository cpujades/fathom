from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

from fathom.core.config import Settings
from fathom.core.errors import ExternalServiceError
from fathom.crud.supabase.summaries import (
    SummaryGenerationLostError,
    SummaryPreparation,
    update_summary_markdown,
)
from fathom.orchestration.summaries import (
    SummaryResolution,
    _create_evidence_summary,
    resolve_summary,
)
from fathom.schemas.briefing_contract import BriefingContract
from fathom.schemas.transcripts import TranscriptSegment
from supabase import AsyncClient


class SummaryLifecycleOrchestrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_timestamped_transcript_uses_separate_evidence_cache_and_generator(
        self,
    ) -> None:
        settings = cast(
            Settings,
            SimpleNamespace(
                openrouter_api_key="test-key",
                provider_summary_deadline_seconds=30,
            ),
        )
        admin_client = cast(AsyncClient, object())
        segments = (
            TranscriptSegment(
                segment_index=0,
                start_seconds=0,
                end_seconds=10,
                text="Evidence.",
            ),
        )
        expected = SummaryResolution(
            summary_id="11111111-1111-1111-1111-111111111111",
            markdown="# Evidence",
            cache_hit=False,
            flush_count=1,
        )

        with (
            patch(
                "fathom.orchestration.summaries._fetch_cached_summary",
                AsyncMock(return_value=None),
            ) as fetch_cached,
            patch(
                "fathom.orchestration.summaries.prepare_summary",
                AsyncMock(
                    return_value=SummaryPreparation(
                        summary={"id": expected.summary_id, "status": "pending"},
                        resolution_type="created",
                    )
                ),
            ) as prepare,
            patch(
                "fathom.orchestration.summaries._create_evidence_summary",
                AsyncMock(return_value=expected),
            ) as create_evidence,
        ):
            result = await resolve_summary(
                job_id="22222222-2222-2222-2222-222222222222",
                user_id="33333333-3333-3333-3333-333333333333",
                requested_summary_id="44444444-4444-4444-4444-444444444444",
                transcript_id="55555555-5555-5555-5555-555555555555",
                transcript_segments=segments,
                settings=settings,
                admin_client=admin_client,
                job_start=0,
                lease_token="66666666-6666-6666-6666-666666666666",
            )

        self.assertEqual(result, expected)
        self.assertEqual(
            fetch_cached.await_args.kwargs["prompt_key"],
            "briefing-v6-evidence-links",
        )
        self.assertEqual(
            prepare.await_args.kwargs["prompt_key"],
            "briefing-v6-evidence-links",
        )
        create_evidence.assert_awaited_once()

    async def test_draft_update_rejects_lost_generation_token(self) -> None:
        query = MagicMock()
        query.execute = AsyncMock(return_value=SimpleNamespace(data=False))
        client = MagicMock()
        client.rpc.return_value = query

        with self.assertRaises(SummaryGenerationLostError):
            await update_summary_markdown(
                cast(AsyncClient, client),
                summary_id="11111111-1111-1111-1111-111111111111",
                generation_token="66666666-6666-6666-6666-666666666666",
                summary_markdown="# Stale draft",
            )

        client.rpc.assert_called_once_with(
            "update_summary_draft",
            {
                "p_summary_id": "11111111-1111-1111-1111-111111111111",
                "p_generation_token": "66666666-6666-6666-6666-666666666666",
                "p_summary_markdown": "# Stale draft",
            },
        )

    async def test_prepare_race_returns_newly_ready_cache(self) -> None:
        settings = cast(Settings, SimpleNamespace(openrouter_api_key="test-key"))
        admin_client = cast(AsyncClient, object())
        expected = SummaryResolution(
            summary_id="11111111-1111-1111-1111-111111111111",
            markdown="",
            cache_hit=True,
        )

        with (
            patch(
                "fathom.orchestration.summaries._fetch_cached_summary",
                AsyncMock(return_value=None),
            ),
            patch(
                "fathom.orchestration.summaries.prepare_summary",
                AsyncMock(
                    return_value=SummaryPreparation(
                        summary={"id": expected.summary_id, "status": "ready"},
                        resolution_type="ready",
                    )
                ),
            ),
            patch(
                "fathom.orchestration.summaries._use_cached_summary",
                AsyncMock(return_value=expected),
            ) as use_cached,
        ):
            result = await resolve_summary(
                job_id="22222222-2222-2222-2222-222222222222",
                user_id="33333333-3333-3333-3333-333333333333",
                requested_summary_id="44444444-4444-4444-4444-444444444444",
                transcript_id="55555555-5555-5555-5555-555555555555",
                transcript_segments=(
                    TranscriptSegment(segment_index=0, start_seconds=0, end_seconds=1, text="Transcript"),
                ),
                settings=settings,
                admin_client=admin_client,
                job_start=0,
                lease_token="66666666-6666-6666-6666-666666666666",
            )

        self.assertEqual(result, expected)
        use_cached.assert_awaited_once()

    async def test_live_pending_producer_waits_without_consuming_job_attempts(self) -> None:
        settings = cast(Settings, SimpleNamespace(openrouter_api_key="test-key"))
        admin_client = cast(AsyncClient, object())
        summary_id = "11111111-1111-1111-1111-111111111111"
        expected = SummaryResolution(
            summary_id=summary_id,
            markdown="",
            cache_hit=True,
        )

        with (
            patch(
                "fathom.orchestration.summaries._fetch_cached_summary",
                AsyncMock(return_value=None),
            ),
            patch(
                "fathom.orchestration.summaries.prepare_summary",
                AsyncMock(
                    side_effect=[
                        SummaryPreparation(
                            summary={"id": summary_id, "status": "pending"},
                            resolution_type="in_progress",
                        ),
                        SummaryPreparation(
                            summary={"id": summary_id, "status": "pending"},
                            resolution_type="in_progress",
                        ),
                        SummaryPreparation(
                            summary={"id": summary_id, "status": "ready"},
                            resolution_type="ready",
                        ),
                    ]
                ),
            ),
            patch("fathom.orchestration.summaries.record_job_event_best_effort", AsyncMock()),
            patch("fathom.orchestration.summaries.update_job_progress", AsyncMock()) as update_progress,
            patch("fathom.orchestration.summaries.asyncio.sleep", AsyncMock()) as sleep,
            patch(
                "fathom.orchestration.summaries._use_cached_summary",
                AsyncMock(return_value=expected),
            ) as use_cached,
        ):
            result = await resolve_summary(
                job_id="22222222-2222-2222-2222-222222222222",
                user_id="33333333-3333-3333-3333-333333333333",
                requested_summary_id="44444444-4444-4444-4444-444444444444",
                transcript_id="55555555-5555-5555-5555-555555555555",
                transcript_segments=(
                    TranscriptSegment(segment_index=0, start_seconds=0, end_seconds=1, text="Transcript"),
                ),
                settings=settings,
                admin_client=admin_client,
                job_start=0,
                lease_token="66666666-6666-6666-6666-666666666666",
            )

        self.assertEqual(result, expected)
        self.assertEqual(sleep.await_count, 2)
        self.assertEqual(update_progress.await_count, 2)
        use_cached.assert_awaited_once()

    async def test_summary_rejects_transcript_without_timestamp_evidence(self) -> None:
        with self.assertRaisesRegex(ExternalServiceError, "Timestamped transcript evidence"):
            await resolve_summary(
                job_id="22222222-2222-2222-2222-222222222222",
                user_id="33333333-3333-3333-3333-333333333333",
                requested_summary_id="44444444-4444-4444-4444-444444444444",
                transcript_id="55555555-5555-5555-5555-555555555555",
                transcript_segments=(),
                settings=cast(Settings, SimpleNamespace()),
                admin_client=cast(AsyncClient, object()),
                job_start=0,
                lease_token="66666666-6666-6666-6666-666666666666",
            )

    async def test_evidence_summary_is_rendered_and_persisted_before_ready(
        self,
    ) -> None:
        settings = cast(
            Settings,
            SimpleNamespace(
                openrouter_api_key="test-key",
                provider_summary_deadline_seconds=30,
            ),
        )
        admin_client = cast(AsyncClient, object())
        segments = (
            TranscriptSegment(
                segment_index=0,
                start_seconds=0,
                end_seconds=10,
                text="Evidence.",
            ),
        )
        contract = cast(BriefingContract, object())
        order: list[str] = []
        rendered_video_ids: list[str | None] = []

        async def generate(*_: Any, **__: Any) -> BriefingContract:
            order.append("generate")
            return contract

        def render(*_: Any, **kwargs: Any) -> str:
            order.append("render")
            rendered_video_ids.append(kwargs.get("source_video_id"))
            return "# Evidence\n"

        async def update(*_: Any, **__: Any) -> None:
            order.append("draft")

        async def ready(*_: Any, **__: Any) -> None:
            order.append("ready")

        async def complete(**_: Any) -> None:
            order.append("event")

        with (
            patch(
                "fathom.orchestration.summaries.record_job_event_best_effort",
                AsyncMock(),
            ),
            patch(
                "fathom.orchestration.summaries.update_job_progress",
                AsyncMock(),
            ),
            patch(
                "fathom.orchestration.summaries.summarize_transcript_with_evidence",
                side_effect=generate,
            ),
            patch(
                "fathom.orchestration.summaries.render_briefing",
                side_effect=render,
            ),
            patch(
                "fathom.orchestration.summaries.update_summary_markdown",
                side_effect=update,
            ),
            patch(
                "fathom.orchestration.summaries._record_first_markdown",
                AsyncMock(),
            ),
            patch(
                "fathom.orchestration.summaries.mark_summary_ready",
                side_effect=ready,
            ),
            patch(
                "fathom.orchestration.summaries._record_summary_completed",
                side_effect=complete,
            ),
        ):
            result = await _create_evidence_summary(
                job_id="22222222-2222-2222-2222-222222222222",
                summary_id="11111111-1111-1111-1111-111111111111",
                transcript_id="55555555-5555-5555-5555-555555555555",
                transcript_segments=segments,
                source_video_id="source-video",
                settings=settings,
                admin_client=admin_client,
                job_start=0,
                lease_token="66666666-6666-6666-6666-666666666666",
            )

        self.assertEqual(order, ["generate", "render", "draft", "ready", "event"])
        self.assertEqual(rendered_video_ids, ["source-video"])
        self.assertEqual(result.markdown, "# Evidence\n")
        self.assertEqual(result.flush_count, 1)

    async def test_failed_evidence_generation_is_marked_for_safe_takeover(self) -> None:
        settings = cast(
            Settings,
            SimpleNamespace(
                openrouter_api_key="test-key",
                provider_summary_deadline_seconds=30,
            ),
        )
        admin_client = cast(AsyncClient, object())
        segments = (TranscriptSegment(segment_index=0, start_seconds=0, end_seconds=10, text="Evidence."),)

        with (
            patch("fathom.orchestration.summaries.record_job_event_best_effort", AsyncMock()),
            patch("fathom.orchestration.summaries.update_job_progress", AsyncMock()),
            patch(
                "fathom.orchestration.summaries.summarize_transcript_with_evidence",
                AsyncMock(side_effect=RuntimeError("provider failed")),
            ),
            patch(
                "fathom.orchestration.summaries.mark_summary_failed",
                AsyncMock(return_value=True),
            ) as mark_failed,
        ):
            with self.assertRaisesRegex(RuntimeError, "provider failed"):
                await _create_evidence_summary(
                    job_id="22222222-2222-2222-2222-222222222222",
                    summary_id="11111111-1111-1111-1111-111111111111",
                    transcript_id="55555555-5555-5555-5555-555555555555",
                    transcript_segments=segments,
                    source_video_id="source-video",
                    settings=settings,
                    admin_client=admin_client,
                    job_start=0,
                    lease_token="66666666-6666-6666-6666-666666666666",
                )

        mark_failed.assert_awaited_once_with(
            admin_client,
            summary_id="11111111-1111-1111-1111-111111111111",
            generation_token="66666666-6666-6666-6666-666666666666",
        )


if __name__ == "__main__":
    unittest.main()

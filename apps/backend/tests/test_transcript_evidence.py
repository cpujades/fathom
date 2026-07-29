from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, call

from fathom.core.errors import ExternalServiceError
from fathom.crud.supabase.transcripts import (
    create_transcript,
    fetch_transcript_segments,
)
from fathom.schemas.transcripts import (
    CitationResolutionError,
    TranscriptSegment,
    resolve_transcript_citation,
)
from fathom.services.transcriber import _extract_groq_transcription
from supabase import AsyncClient


def _segments() -> tuple[TranscriptSegment, ...]:
    return (
        TranscriptSegment(
            segment_index=0,
            start_seconds=8.25,
            end_seconds=12.0,
            text="The first piece of evidence.",
        ),
        TranscriptSegment(
            segment_index=1,
            start_seconds=12.0,
            end_seconds=17.5,
            text="The second piece of evidence.",
        ),
        TranscriptSegment(
            segment_index=2,
            start_seconds=19.0,
            end_seconds=22.0,
            text="A separate point.",
        ),
    )


class TranscriptCitationTests(unittest.TestCase):
    def test_resolves_contiguous_segments_to_exact_evidence_window(self) -> None:
        citation = resolve_transcript_citation(_segments(), (0, 1))

        self.assertEqual(citation.segment_indexes, (0, 1))
        self.assertEqual(citation.start_seconds, 8.25)
        self.assertEqual(citation.end_seconds, 17.5)
        self.assertEqual(
            citation.evidence_text,
            "The first piece of evidence. The second piece of evidence.",
        )

    def test_rejects_unknown_segment(self) -> None:
        with self.assertRaisesRegex(CitationResolutionError, "Unknown"):
            resolve_transcript_citation(_segments(), (3,))

    def test_rejects_non_contiguous_or_reordered_segments(self) -> None:
        with self.assertRaisesRegex(CitationResolutionError, "contiguous"):
            resolve_transcript_citation(_segments(), (0, 2))
        with self.assertRaisesRegex(CitationResolutionError, "unique and ordered"):
            resolve_transcript_citation(_segments(), (1, 0))

    def test_segment_and_citation_collections_are_immutable(self) -> None:
        segments = _segments()
        citation = resolve_transcript_citation(segments, (0,))

        with self.assertRaises((AttributeError, TypeError)):
            segments[0].text = "changed"  # type: ignore[misc]
        with self.assertRaises((AttributeError, TypeError)):
            citation.segment_indexes += (1,)  # type: ignore[misc]


class TranscriptProviderParsingTests(unittest.TestCase):
    def test_legacy_or_degraded_response_keeps_full_text_without_fabricated_segments(
        self,
    ) -> None:
        result = _extract_groq_transcription(SimpleNamespace(text="Compatible full transcript"))

        self.assertEqual(result.text, "Compatible full transcript")
        self.assertEqual(result.segments, ())


class TranscriptEvidenceCrudTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_transcript_persists_text_and_segments_transactionally(self) -> None:
        execute = AsyncMock(
            return_value=SimpleNamespace(
                data={
                    "id": "11111111-1111-1111-1111-111111111111",
                    "url_hash": "url-hash",
                    "transcript_text": "Full transcript",
                }
            )
        )
        rpc_query = SimpleNamespace(execute=execute)
        client = MagicMock()
        client.rpc.return_value = rpc_query

        result = await create_transcript(
            cast(AsyncClient, client),
            url_hash="url-hash",
            video_id="video-id",
            transcript_text="Full transcript",
            provider_model="groq:whisper-large-v3-turbo",
            segments=_segments(),
            source_title="Episode",
        )

        self.assertEqual(result["id"], "11111111-1111-1111-1111-111111111111")
        client.rpc.assert_called_once_with(
            "create_transcript_with_segments",
            {
                "p_url_hash": "url-hash",
                "p_video_id": "video-id",
                "p_transcript_text": "Full transcript",
                "p_provider_model": "groq:whisper-large-v3-turbo",
                "p_segments": [
                    {
                        "segment_index": 0,
                        "start_seconds": 8.25,
                        "end_seconds": 12.0,
                        "text": "The first piece of evidence.",
                    },
                    {
                        "segment_index": 1,
                        "start_seconds": 12.0,
                        "end_seconds": 17.5,
                        "text": "The second piece of evidence.",
                    },
                    {
                        "segment_index": 2,
                        "start_seconds": 19.0,
                        "end_seconds": 22.0,
                        "text": "A separate point.",
                    },
                ],
                "p_source_title": "Episode",
                "p_source_author": None,
                "p_source_description": None,
                "p_source_keywords": None,
                "p_source_views": None,
                "p_source_likes": None,
                "p_source_length_seconds": None,
            },
        )
        execute.assert_awaited_once()

    async def test_fetch_segments_uses_stable_index_order(self) -> None:
        query = MagicMock()
        query.select.return_value = query
        query.eq.return_value = query
        query.order.return_value = query
        query.execute = AsyncMock(
            return_value=SimpleNamespace(
                data=[
                    {
                        "segment_index": 0,
                        "start_seconds": 1.0,
                        "end_seconds": 2.0,
                        "segment_text": "First",
                    },
                    {
                        "segment_index": 1,
                        "start_seconds": 2.0,
                        "end_seconds": 3.0,
                        "segment_text": "Second",
                    },
                ]
            )
        )
        client = MagicMock()
        client.table.return_value = query

        segments = await fetch_transcript_segments(
            cast(AsyncClient, client),
            transcript_id="11111111-1111-1111-1111-111111111111",
        )

        self.assertEqual([segment.text for segment in segments], ["First", "Second"])
        self.assertEqual(
            query.method_calls,
            [
                call.select("segment_index,start_seconds,end_seconds,segment_text"),
                call.eq(
                    "transcript_id",
                    "11111111-1111-1111-1111-111111111111",
                ),
                call.order("segment_index"),
                call.execute(),
            ],
        )

    async def test_fetch_segments_rejects_non_contiguous_database_rows(self) -> None:
        query = MagicMock()
        query.select.return_value = query
        query.eq.return_value = query
        query.order.return_value = query
        query.execute = AsyncMock(
            return_value=SimpleNamespace(
                data=[
                    {
                        "segment_index": 1,
                        "start_seconds": 1.0,
                        "end_seconds": 2.0,
                        "segment_text": "Wrong index",
                    }
                ]
            )
        )
        client = MagicMock()
        client.table.return_value = query

        with self.assertRaisesRegex(ExternalServiceError, "non-contiguous"):
            await fetch_transcript_segments(
                cast(AsyncClient, client),
                transcript_id="11111111-1111-1111-1111-111111111111",
            )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import os
import unittest

import asyncpg

DATABASE_URL = os.getenv("FATHOM_TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "FATHOM_TEST_DATABASE_URL is not configured")
class TranscriptEvidenceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.connection = await asyncpg.connect(DATABASE_URL)
        await self._cleanup()

    async def asyncTearDown(self) -> None:
        await self._cleanup()
        await self.connection.close()

    async def _cleanup(self) -> None:
        await self.connection.execute(
            """
            delete from public.transcripts
            where url_hash = 'transcript-evidence-integration'
              and provider_model = 'groq:test-evidence';
            """
        )

    async def _create(self, *, transcript_text: str, segments: list[dict[str, object]]) -> dict[str, object]:
        result = await self.connection.fetchval(
            """
            select public.create_transcript_with_segments(
              $1, $2, $3, $4, $5::jsonb,
              $6, $7, $8, $9::text[], $10, $11, $12
            )
            """,
            "transcript-evidence-integration",
            "evidence-video",
            transcript_text,
            "groq:test-evidence",
            json.dumps(segments),
            "Evidence episode",
            None,
            None,
            None,
            None,
            None,
            60,
        )
        return json.loads(result) if isinstance(result, str) else dict(result)

    async def test_command_is_atomic_idempotent_and_segments_are_immutable(self) -> None:
        original_segments = [
            {
                "segment_index": 0,
                "start_seconds": 1.0,
                "end_seconds": 2.0,
                "text": "Original evidence.",
            }
        ]
        first = await self._create(
            transcript_text="Original transcript",
            segments=original_segments,
        )
        replay = await self._create(
            transcript_text="Replacement transcript",
            segments=[
                {
                    "segment_index": 0,
                    "start_seconds": 10.0,
                    "end_seconds": 20.0,
                    "text": "Replacement evidence.",
                }
            ],
        )

        self.assertEqual(first["id"], replay["id"])
        transcript = await self.connection.fetchrow(
            """
            select transcript_text
            from public.transcripts
            where id = $1
            """,
            first["id"],
        )
        segments = await self.connection.fetch(
            """
            select segment_index, start_seconds, end_seconds, segment_text
            from public.transcript_segments
            where transcript_id = $1
            order by segment_index
            """,
            first["id"],
        )

        self.assertEqual(transcript["transcript_text"], "Original transcript")
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["start_seconds"], 1.0)
        self.assertEqual(segments[0]["segment_text"], "Original evidence.")

    async def test_service_role_has_append_only_segment_privileges(self) -> None:
        privileges = await self.connection.fetchrow(
            """
            select
              has_table_privilege('service_role', 'public.transcript_segments', 'select') as can_select,
              has_table_privilege('service_role', 'public.transcript_segments', 'insert') as can_insert,
              has_table_privilege('service_role', 'public.transcript_segments', 'update') as can_update,
              has_table_privilege('service_role', 'public.transcript_segments', 'delete') as can_delete,
              has_function_privilege(
                'service_role',
                'public.create_transcript_with_segments(text,text,text,text,jsonb,text,text,text,text[],bigint,bigint,integer)',
                'execute'
              ) as can_execute_command
            """
        )

        self.assertTrue(privileges["can_select"])
        self.assertFalse(privileges["can_insert"])
        self.assertFalse(privileges["can_update"])
        self.assertFalse(privileges["can_delete"])
        self.assertTrue(privileges["can_execute_command"])


if __name__ == "__main__":
    unittest.main()

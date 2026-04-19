from __future__ import annotations

import json
import unittest

from fathom.application.briefings.contract import (
    build_briefing_session_snapshot,
    encode_sse_event,
    normalize_source,
)


class NormalizeSourceTests(unittest.TestCase):
    def test_normalize_youtube_short_url_into_canonical_identity(self) -> None:
        source = normalize_source("https://youtu.be/abc123?t=42")

        self.assertEqual(source.canonical_url, "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(source.source_type, "youtube")
        self.assertEqual(source.source_identity_key, "youtube:abc123")


class BriefingSessionSnapshotTests(unittest.TestCase):
    def test_map_cached_job_into_ready_reused_snapshot(self) -> None:
        source = normalize_source("https://www.youtube.com/watch?v=abc123")
        snapshot = build_briefing_session_snapshot(
            job={
                "id": "11111111-1111-1111-1111-111111111111",
                "status": "succeeded",
                "summary_id": "22222222-2222-2222-2222-222222222222",
                "stage": "cached",
                "progress": 100,
                "status_message": "Summary ready (cached)",
                "error_code": None,
                "error_message": None,
            },
            source=source,
            resolution_type="reused_ready",
        )

        self.assertEqual(snapshot.state, "ready")
        self.assertEqual(snapshot.resolution_type, "reused_ready")
        self.assertEqual(str(snapshot.briefing_id), "22222222-2222-2222-2222-222222222222")
        self.assertEqual(snapshot.message, "Using an existing briefing")
        self.assertEqual(snapshot.source_title, "Untitled YouTube briefing")
        self.assertEqual(snapshot.source_thumbnail_url, "https://i.ytimg.com/vi/abc123/hqdefault.jpg")
        self.assertIsNone(snapshot.source_author)

    def test_map_finalizing_job_into_finalizing_snapshot(self) -> None:
        source = normalize_source("https://www.youtube.com/watch?v=abc123")
        snapshot = build_briefing_session_snapshot(
            job={
                "id": "11111111-1111-1111-1111-111111111111",
                "status": "running",
                "summary_id": "22222222-2222-2222-2222-222222222222",
                "stage": "finalizing",
                "progress": 96,
                "status_message": "Finalizing your briefing",
                "error_code": None,
                "error_message": None,
            },
            source=source,
            summary={
                "summary_markdown": "# Draft",
                "pdf_object_key": None,
            },
            transcript={
                "video_id": "abc123",
                "source_title": "How to Think Better",
                "source_author": "Chris Williamson",
                "source_length_seconds": 5472,
            },
        )

        self.assertEqual(snapshot.state, "finalizing_briefing")
        self.assertEqual(snapshot.message, "Finalizing your briefing")
        self.assertEqual(snapshot.briefing_markdown, "# Draft")
        self.assertFalse(snapshot.briefing_has_pdf)
        self.assertEqual(snapshot.source_title, "How to Think Better")
        self.assertEqual(snapshot.source_author, "Chris Williamson")
        self.assertEqual(snapshot.source_duration_seconds, 5472)
        self.assertEqual(snapshot.source_thumbnail_url, "https://i.ytimg.com/vi/abc123/hqdefault.jpg")


class SseEncodingTests(unittest.TestCase):
    def test_encode_sse_event_with_json_payload(self) -> None:
        payload = {"state": "ready", "briefing_id": "briefing-1"}

        encoded = encode_sse_event(
            event_type="session.ready",
            event_id="evt-1",
            data=payload,
        )

        self.assertIn("id: evt-1\n", encoded)
        self.assertIn("event: session.ready\n", encoded)
        self.assertIn(f"data: {json.dumps(payload, separators=(',', ':'))}\n\n", encoded)


if __name__ == "__main__":
    unittest.main()

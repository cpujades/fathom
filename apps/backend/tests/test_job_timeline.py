from __future__ import annotations

import unittest

from fathom.application.diagnostics.job_timeline import format_job_timeline


class JobTimelineFormattingTests(unittest.TestCase):
    def test_formats_persisted_events(self) -> None:
        output = format_job_timeline(
            {
                "session_id": "job-1",
                "job": {
                    "id": "job-1",
                    "user_id": "user-1",
                    "status": "succeeded",
                    "stage": "completed",
                    "progress": 100,
                    "url": "https://youtube.com/watch?v=test",
                    "duration_seconds": 125,
                },
                "summary": {
                    "id": "summary-1",
                    "summary_model": "openrouter/model",
                    "summary_markdown": "hello world",
                },
                "transcript": {
                    "source_title": "A source",
                    "source_author": "An author",
                    "source_length_seconds": 125,
                },
                "events": [
                    {
                        "created_at": "2026-05-17T15:00:00+00:00",
                        "event_type": "summary_completed",
                        "stage": "summarizing",
                        "message": "Summary completed.",
                        "metadata": {
                            "provider": "openrouter",
                            "model": "openrouter/model",
                            "markdown_chars": 11,
                            "flush_count": 2,
                        },
                    }
                ],
                "events_unavailable": False,
            }
        )

        self.assertIn("Talven job timeline", output)
        self.assertIn("Source: A source by An author (2m 5s)", output)
        self.assertIn("summary_completed [summarizing]", output)
        self.assertIn("markdown_chars=11", output)

    def test_formats_inferred_checkpoints_without_events(self) -> None:
        output = format_job_timeline(
            {
                "session_id": "job-2",
                "job": {
                    "id": "job-2",
                    "user_id": "user-1",
                    "status": "running",
                    "stage": "transcribing",
                    "progress": 30,
                    "url": "https://youtube.com/watch?v=test",
                    "created_at": "2026-05-17T15:00:00+00:00",
                    "claimed_at": "2026-05-17T15:00:02+00:00",
                    "updated_at": "2026-05-17T15:00:20+00:00",
                    "attempt_count": 1,
                },
                "summary": None,
                "transcript": None,
                "events": [],
                "events_unavailable": True,
            }
        )

        self.assertIn("job_events unavailable", output)
        self.assertIn("session_created [queued]", output)
        self.assertIn("job_claimed [running]", output)


if __name__ == "__main__":
    unittest.main()

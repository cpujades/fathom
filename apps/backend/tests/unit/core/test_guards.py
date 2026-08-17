from __future__ import annotations

import unittest

from fathom.application.guards import MAX_VIDEO_DURATION_SECONDS, validate_video_duration
from fathom.core.errors import SourceDurationUnknownError, SourceTooLongError


class VideoDurationGuardTests(unittest.TestCase):
    def test_positive_duration_within_limit_is_allowed(self) -> None:
        validate_video_duration(60)
        validate_video_duration(MAX_VIDEO_DURATION_SECONDS)

    def test_missing_or_non_positive_duration_is_rejected(self) -> None:
        for duration in (None, 0, -1):
            with (
                self.subTest(duration=duration),
                self.assertRaises(SourceDurationUnknownError),
            ):
                validate_video_duration(duration)

    def test_duration_above_limit_is_rejected(self) -> None:
        with self.assertRaises(SourceTooLongError) as raised:
            validate_video_duration(MAX_VIDEO_DURATION_SECONDS + 1)
        self.assertEqual(raised.exception.code, "source_too_long")
        self.assertEqual(raised.exception.details, {"maximum_seconds": MAX_VIDEO_DURATION_SECONDS})


if __name__ == "__main__":
    unittest.main()

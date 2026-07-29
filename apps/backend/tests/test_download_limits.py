from __future__ import annotations

import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

from pydantic import ValidationError

from fathom.core.config import DEFAULT_SOURCE_DOWNLOAD_DEADLINE_SECONDS, Settings
from fathom.crud.supabase.storage_objects import upload_object
from fathom.services.downloader import DownloadError, download_audio
from supabase import AsyncClient


class FakeAudioStream:
    type = "audio"
    subtype = "webm"
    mime_type = "audio/webm"
    abr = "48kbps"

    def __init__(
        self,
        *,
        advertised_size: int | None,
        chunks: list[bytes] | None = None,
        interrupt: bool = False,
    ) -> None:
        self.filesize = advertised_size
        self.filesize_approx = advertised_size
        self.chunks = chunks or []
        self.interrupt = interrupt
        self.download_calls = 0
        self.progress_callback: Callable[[object, bytes, int], None] | None = None

    def download(
        self,
        output_path: str,
        filename: str,
        *,
        timeout: int,
        interrupt_checker: Callable[[], bool],
    ) -> str | None:
        del timeout
        self.download_calls += 1
        target = Path(output_path) / filename
        callback = self.progress_callback
        if callback is None:
            raise AssertionError("progress callback was not configured")
        with target.open("wb") as file_handle:
            for chunk in self.chunks:
                if self.interrupt or interrupt_checker():
                    return None
                file_handle.write(chunk)
                callback(self, chunk, 0)
        return str(target)


def _youtube_factory(stream: FakeAudioStream) -> object:
    def factory(
        _url: str,
        *,
        on_progress_callback: Callable[[object, bytes, int], None],
    ) -> object:
        stream.progress_callback = on_progress_callback
        streams = SimpleNamespace(filter=Mock(return_value=[stream]))
        return SimpleNamespace(
            streams=streams,
            video_id="video-id",
            title="Title",
            author="Author",
            description="Description",
            keywords=[],
            views=1,
            likes=1,
            length=60,
        )

    return factory


class DownloadLimitTests(unittest.TestCase):
    def test_rejects_advertised_oversize_before_download(self) -> None:
        stream = FakeAudioStream(advertised_size=101)
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("fathom.services.downloader.YouTube", _youtube_factory(stream)),
            self.assertRaisesRegex(DownloadError, "100 MB"),
        ):
            download_audio("https://www.youtube.com/watch?v=test", temp_dir, max_bytes=100)

        self.assertEqual(stream.download_calls, 0)

    def test_aborts_unknown_size_when_stream_crosses_limit_and_removes_partial_file(self) -> None:
        stream = FakeAudioStream(
            advertised_size=None,
            chunks=[b"a" * 60, b"b" * 60],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("fathom.services.downloader.YouTube", _youtube_factory(stream)),
                self.assertRaisesRegex(DownloadError, "100 MB"),
            ):
                download_audio(
                    "https://www.youtube.com/watch?v=test",
                    temp_dir,
                    max_bytes=100,
                )

            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_rejects_interrupted_download_and_removes_partial_file(self) -> None:
        stream = FakeAudioStream(
            advertised_size=10,
            chunks=[b"content"],
            interrupt=True,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("fathom.services.downloader.YouTube", _youtube_factory(stream)),
                self.assertRaisesRegex(DownloadError, "did not complete"),
            ):
                download_audio(
                    "https://www.youtube.com/watch?v=test",
                    temp_dir,
                    max_bytes=100,
                )

            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_aborts_download_after_total_deadline(self) -> None:
        stream = FakeAudioStream(
            advertised_size=10,
            chunks=[b"content"],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("fathom.services.downloader.YouTube", _youtube_factory(stream)),
                patch(
                    "fathom.services.downloader.time.monotonic",
                    side_effect=[0.0, 11.0, 11.0],
                ),
                self.assertRaisesRegex(DownloadError, "deadline exceeded"),
            ):
                download_audio(
                    "https://www.youtube.com/watch?v=test",
                    temp_dir,
                    max_bytes=100,
                    deadline_seconds=10,
                )

            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_valid_download_returns_actual_size(self) -> None:
        stream = FakeAudioStream(
            advertised_size=7,
            chunks=[b"content"],
        )
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("fathom.services.downloader.YouTube", _youtube_factory(stream)),
        ):
            result = download_audio(
                "https://www.youtube.com/watch?v=test",
                temp_dir,
                max_bytes=100,
            )

            self.assertEqual(result.filesize_bytes, 7)
            self.assertEqual(result.path.read_bytes(), b"content")


class DownloadDeadlineSettingsTests(unittest.TestCase):
    def _settings_values(self) -> dict[str, str]:
        return {
            "OPENROUTER_API_KEY": "openrouter",
            "GROQ_API_KEY": "groq",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "publishable",
            "SUPABASE_SECRET_KEY": "secret",
        }

    def test_download_deadline_has_safe_default(self) -> None:
        settings = Settings.model_validate(self._settings_values())

        self.assertEqual(
            settings.source_download_deadline_seconds,
            DEFAULT_SOURCE_DOWNLOAD_DEADLINE_SECONDS,
        )

    def test_download_deadline_must_be_positive_and_bounded(self) -> None:
        values = self._settings_values()
        values["SOURCE_DOWNLOAD_DEADLINE_SECONDS"] = "0"
        with self.assertRaises(ValidationError):
            Settings.model_validate(values)

        values["SOURCE_DOWNLOAD_DEADLINE_SECONDS"] = "3601"
        with self.assertRaises(ValidationError):
            Settings.model_validate(values)


class StreamingStorageUploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_object_passes_path_without_reading_file_into_memory(self) -> None:
        bucket_client = SimpleNamespace(upload=AsyncMock())
        storage = SimpleNamespace(from_=Mock(return_value=bucket_client))
        client = cast(AsyncClient, SimpleNamespace(storage=storage))
        source_path = Path("/tmp/audio.webm")

        await upload_object(
            client,
            bucket="audio",
            object_key="jobs/audio.webm",
            data=source_path,
            content_type="audio/webm",
        )

        bucket_client.upload.assert_awaited_once_with(
            "jobs/audio.webm",
            source_path,
            {"content-type": "audio/webm", "upsert": "true"},
        )


if __name__ == "__main__":
    unittest.main()

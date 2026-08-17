from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import unittest
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

from fathom.core.errors import ExternalServiceError, ForbiddenError, NotFoundError, RateLimitError
from fathom.crud.supabase.storage_objects import delete_object_with_retry, upload_object
from fathom.services.downloader import (
    SOURCE_DOWNLOAD_TIMEOUT_SECONDS,
    SOURCE_METADATA_TIMEOUT_SECONDS,
    AudioTooLargeError,
    DownloadError,
    download_audio,
    download_audio_with_deadline,
    fetch_video_metadata_with_deadline,
)
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
            self.assertRaisesRegex(AudioTooLargeError, "100 MB"),
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
                self.assertRaisesRegex(AudioTooLargeError, "100 MB"),
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

    def test_cancellation_interrupts_download_and_removes_partial_file(self) -> None:
        stream = FakeAudioStream(
            advertised_size=10,
            chunks=[b"content"],
        )
        cancel_event = threading.Event()
        cancel_event.set()
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("fathom.services.downloader.YouTube", _youtube_factory(stream)),
                self.assertRaisesRegex(DownloadError, "cancelled"),
            ):
                download_audio(
                    "https://www.youtube.com/watch?v=test",
                    temp_dir,
                    max_bytes=100,
                    cancel_event=cancel_event,
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


class DownloadTimeoutConstantTests(unittest.TestCase):
    def test_source_timeout_constants(self) -> None:
        self.assertEqual(SOURCE_DOWNLOAD_TIMEOUT_SECONDS, 300.0)
        self.assertEqual(SOURCE_METADATA_TIMEOUT_SECONDS, 30.0)


class YouTubeWorkerDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_preserves_the_deterministic_audio_size_error(self) -> None:
        process = SimpleNamespace(
            returncode=1,
            communicate=AsyncMock(
                return_value=(
                    json.dumps(
                        {
                            "ok": False,
                            "code": "source_audio_too_large",
                            "detail": "Source audio exceeds the supported 100 MB limit.",
                        }
                    ).encode(),
                    b"",
                )
            ),
            kill=Mock(),
            wait=AsyncMock(),
        )
        with (
            patch(
                "fathom.services.downloader.asyncio.create_subprocess_exec",
                AsyncMock(return_value=process),
            ),
            self.assertRaisesRegex(AudioTooLargeError, "100 MB"),
        ):
            await download_audio_with_deadline(
                "https://www.youtube.com/watch?v=test",
                "/tmp",
                deadline_seconds=1,
            )

    async def test_metadata_worker_returns_validated_result(self) -> None:
        process = SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(
                return_value=(
                    json.dumps(
                        {
                            "ok": True,
                            "result": {
                                "video_id": "video-id",
                                "duration_seconds": 60,
                                "title": "Title",
                            },
                        }
                    ).encode(),
                    b"",
                )
            ),
            kill=Mock(),
            wait=AsyncMock(),
        )
        create_process = AsyncMock(return_value=process)
        with (
            patch(
                "fathom.services.downloader.asyncio.create_subprocess_exec",
                create_process,
            ),
            patch.dict("os.environ", {"OPENROUTER_API_KEY": "secret", "PATH": "/usr/bin"}),
        ):
            result = await fetch_video_metadata_with_deadline(
                "https://www.youtube.com/watch?v=test",
                deadline_seconds=1,
            )

        self.assertEqual(result.video_id, "video-id")
        self.assertEqual(result.duration_seconds, 60)
        worker_env = create_process.await_args.kwargs["env"]
        self.assertEqual(worker_env["PATH"], "/usr/bin")
        self.assertNotIn("OPENROUTER_API_KEY", worker_env)

    async def test_metadata_worker_is_killed_at_the_overall_deadline(self) -> None:
        async def never_returns(_request: bytes) -> tuple[bytes, bytes]:
            await asyncio.sleep(60)
            return b"", b""

        process = SimpleNamespace(
            returncode=None,
            communicate=never_returns,
            kill=Mock(),
            wait=AsyncMock(),
        )
        with (
            patch(
                "fathom.services.downloader.asyncio.create_subprocess_exec",
                AsyncMock(return_value=process),
            ),
            self.assertRaisesRegex(DownloadError, "deadline exceeded"),
        ):
            await fetch_video_metadata_with_deadline(
                "https://www.youtube.com/watch?v=test",
                deadline_seconds=0.001,
            )

        process.kill.assert_called_once()
        process.wait.assert_awaited_once()

    async def test_metadata_worker_is_reaped_after_unexpected_ipc_failure(self) -> None:
        process = SimpleNamespace(
            returncode=None,
            communicate=AsyncMock(side_effect=OSError("broken subprocess pipe")),
            kill=Mock(),
            wait=AsyncMock(),
        )
        with (
            patch(
                "fathom.services.downloader.asyncio.create_subprocess_exec",
                AsyncMock(return_value=process),
            ),
            self.assertRaisesRegex(DownloadError, "source request failed"),
        ):
            await fetch_video_metadata_with_deadline(
                "https://www.youtube.com/watch?v=test",
                deadline_seconds=1,
            )

        process.kill.assert_called_once()
        process.wait.assert_awaited_once()


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

    async def test_cleanup_retries_temporary_failures_with_bounded_backoff(self) -> None:
        delete = AsyncMock(
            side_effect=[
                ExternalServiceError("temporary"),
                RateLimitError("slow down"),
                None,
            ]
        )
        with (
            patch("fathom.crud.supabase.storage_objects.delete_object", delete),
            patch("fathom.crud.supabase.storage_objects.asyncio.sleep", AsyncMock()) as sleep,
        ):
            await delete_object_with_retry(
                cast(AsyncClient, object()),
                bucket="audio",
                object_key="temporary/source.webm",
            )

        self.assertEqual(delete.await_count, 3)
        self.assertEqual(
            [call.args[0] for call in sleep.await_args_list],
            [0.2, 0.4],
        )

    async def test_cleanup_treats_an_already_missing_object_as_success(self) -> None:
        delete = AsyncMock(side_effect=NotFoundError("already deleted"))
        with (
            patch("fathom.crud.supabase.storage_objects.delete_object", delete),
            patch("fathom.crud.supabase.storage_objects.asyncio.sleep", AsyncMock()) as sleep,
        ):
            await delete_object_with_retry(
                cast(AsyncClient, object()),
                bucket="audio",
                object_key="temporary/source.webm",
            )

        delete.assert_awaited_once()
        sleep.assert_not_awaited()

    async def test_cleanup_does_not_retry_permanent_permission_failures(self) -> None:
        delete = AsyncMock(side_effect=ForbiddenError("denied"))
        with (
            patch("fathom.crud.supabase.storage_objects.delete_object", delete),
            patch("fathom.crud.supabase.storage_objects.asyncio.sleep", AsyncMock()) as sleep,
            self.assertRaises(ForbiddenError),
        ):
            await delete_object_with_retry(
                cast(AsyncClient, object()),
                bucket="audio",
                object_key="temporary/source.webm",
            )

        delete.assert_awaited_once()
        sleep.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import pathlib
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol, cast

from pytubefix import YouTube

from fathom.core.config import DEFAULT_SOURCE_DOWNLOAD_DEADLINE_SECONDS
from fathom.core.errors import ExternalServiceError

MAX_AUDIO_FILE_BYTES = 100_000_000
DOWNLOAD_REQUEST_TIMEOUT_SECONDS = 60


class DownloadError(ExternalServiceError):
    pass


class AudioStream(Protocol):
    type: str | None
    subtype: str | None
    mime_type: str | None
    abr: str | None
    filesize: int | None
    filesize_approx: int | None

    def download(
        self,
        output_path: str,
        filename: str,
        *,
        timeout: int,
        interrupt_checker: Callable[[], bool],
    ) -> str | None: ...


@dataclass(frozen=True)
class DownloadResult:
    path: pathlib.Path
    video_id: str | None
    mime_type: str | None
    subtype: str | None
    filesize_bytes: int | None
    title: str | None
    author: str | None
    description: str | None
    keywords: list[str] | None
    views: int | None
    likes: int | None
    length_seconds: int | None


@dataclass(frozen=True)
class VideoMetadata:
    video_id: str | None
    duration_seconds: int | None
    title: str | None


class _DownloadLimitExceeded(Exception):
    pass


@dataclass
class _DownloadBudget:
    max_bytes: int
    deadline_seconds: float
    started_at: float
    cancel_event: threading.Event | None = None
    downloaded_bytes: int = 0

    def on_progress(self, _stream: object, chunk: bytes, _bytes_remaining: int) -> None:
        self.downloaded_bytes += len(chunk)
        if self.downloaded_bytes > self.max_bytes:
            raise _DownloadLimitExceeded

    def should_interrupt(self) -> bool:
        if self.cancel_event is not None and self.cancel_event.is_set():
            return True
        return time.monotonic() - self.started_at >= self.deadline_seconds

    def deadline_exceeded(self) -> bool:
        return time.monotonic() - self.started_at >= self.deadline_seconds


def _parse_abr_kbps(abr: str | None) -> int | None:
    if not abr:
        return None
    abr = abr.lower().replace("kbps", "").strip()
    try:
        return int(float(abr))
    except ValueError:
        return None


def _audio_stream_sort_key(item: tuple[int | None, int | None, AudioStream]) -> tuple[int, int]:
    filesize, abr_kbps, _stream = item
    return (filesize or 2**31 - 1, abr_kbps or 2**31 - 1)


def _pick_fastest_audio_stream(streams: Iterable[AudioStream]) -> AudioStream:
    candidates: list[tuple[int | None, int | None, AudioStream]] = []
    for stream in streams:
        if getattr(stream, "type", None) != "audio":
            continue
        filesize = getattr(stream, "filesize", None) or getattr(stream, "filesize_approx", None)
        abr_kbps = _parse_abr_kbps(getattr(stream, "abr", None))
        candidates.append((filesize, abr_kbps, stream))

    if not candidates:
        raise DownloadError("No audio streams available for this URL.")

    candidates.sort(key=_audio_stream_sort_key)
    return candidates[0][2]


def _read_yt_metadata(
    yt: YouTube,
) -> tuple[str | None, str | None, list[str] | None, int | None, int | None, int | None]:
    keywords = getattr(yt, "keywords", None)
    if keywords is not None and not isinstance(keywords, list):
        keywords = None
    return (
        getattr(yt, "title", None),
        getattr(yt, "author", None),
        keywords,
        getattr(yt, "views", None),
        getattr(yt, "likes", None),
        getattr(yt, "length", None),
    )


def download_audio(
    url: str,
    output_dir: str,
    *,
    max_bytes: int = MAX_AUDIO_FILE_BYTES,
    deadline_seconds: float = DEFAULT_SOURCE_DOWNLOAD_DEADLINE_SECONDS,
    cancel_event: threading.Event | None = None,
) -> DownloadResult:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be greater than zero")
    if deadline_seconds <= 0:
        raise ValueError("deadline_seconds must be greater than zero")

    budget = _DownloadBudget(
        max_bytes=max_bytes,
        deadline_seconds=deadline_seconds,
        started_at=time.monotonic(),
        cancel_event=cancel_event,
    )
    try:
        yt = YouTube(url, on_progress_callback=budget.on_progress)
    except Exception as exc:  # pragma: no cover - external failure
        raise DownloadError("Failed to initialize YouTube downloader.") from exc

    streams = cast(Iterable[AudioStream], yt.streams.filter(only_audio=True))
    stream = _pick_fastest_audio_stream(streams)
    advertised_size = getattr(stream, "filesize", None) or getattr(stream, "filesize_approx", None)
    if advertised_size is not None and advertised_size > max_bytes:
        raise DownloadError("Source audio exceeds the supported 100 MB limit.")

    file_id = uuid.uuid4().hex
    filename = f"{file_id}.{stream.subtype or 'bin'}"
    output_path = pathlib.Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    target_path = output_path / filename

    try:
        downloaded = stream.download(
            output_path=str(output_path),
            filename=filename,
            timeout=max(
                1,
                min(int(deadline_seconds), DOWNLOAD_REQUEST_TIMEOUT_SECONDS),
            ),
            interrupt_checker=budget.should_interrupt,
        )
    except _DownloadLimitExceeded as exc:
        target_path.unlink(missing_ok=True)
        raise DownloadError("Source audio exceeds the supported 100 MB limit.") from exc
    except Exception as exc:  # pragma: no cover - external failure
        target_path.unlink(missing_ok=True)
        raise DownloadError("Failed to download audio stream.") from exc

    if cancel_event is not None and cancel_event.is_set():
        target_path.unlink(missing_ok=True)
        raise DownloadError("Source audio download was cancelled.")
    if budget.deadline_exceeded():
        target_path.unlink(missing_ok=True)
        raise DownloadError("Source audio download deadline exceeded.")
    if not downloaded:
        target_path.unlink(missing_ok=True)
        raise DownloadError("Audio download did not complete.")

    path = pathlib.Path(downloaded)
    try:
        filesize_bytes = path.stat().st_size
    except OSError:
        filesize_bytes = None
    if filesize_bytes is not None and filesize_bytes > max_bytes:
        path.unlink(missing_ok=True)
        raise DownloadError("Source audio exceeds the supported 100 MB limit.")

    title, author, keywords, views, likes, length_seconds = _read_yt_metadata(yt)

    return DownloadResult(
        path=path,
        video_id=getattr(yt, "video_id", None),
        mime_type=getattr(stream, "mime_type", None),
        subtype=getattr(stream, "subtype", None),
        filesize_bytes=filesize_bytes,
        title=title,
        author=author,
        description=getattr(yt, "description", None),
        keywords=keywords,
        views=views,
        likes=likes,
        length_seconds=length_seconds,
    )


def fetch_video_metadata(url: str) -> VideoMetadata:
    try:
        yt = YouTube(url)
    except Exception as exc:  # pragma: no cover - external failure
        raise DownloadError("Failed to fetch video metadata.") from exc

    duration = getattr(yt, "length", None)
    duration_seconds = duration if isinstance(duration, int) else None
    title = getattr(yt, "title", None)
    if not isinstance(title, str):
        title = None

    return VideoMetadata(
        video_id=getattr(yt, "video_id", None),
        duration_seconds=duration_seconds,
        title=title,
    )

from __future__ import annotations

import pathlib
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, cast

from pytubefix import YouTube

from fathom.core.errors import ExternalServiceError


class DownloadError(ExternalServiceError):
    pass


class AudioStream(Protocol):
    type: str | None
    subtype: str | None
    mime_type: str | None
    abr: str | None
    filesize: int | None
    filesize_approx: int | None

    def download(self, output_path: str, filename: str) -> str: ...


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


def download_audio(url: str, output_dir: str) -> DownloadResult:
    try:
        yt = YouTube(url)
    except Exception as exc:  # pragma: no cover - external failure
        raise DownloadError("Failed to initialize YouTube downloader.") from exc

    streams = cast(Iterable[AudioStream], yt.streams.filter(only_audio=True))
    stream = _pick_fastest_audio_stream(streams)
    file_id = uuid.uuid4().hex
    filename = f"{file_id}.{stream.subtype or 'bin'}"
    output_path = pathlib.Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        downloaded = stream.download(output_path=str(output_path), filename=filename)
    except Exception as exc:  # pragma: no cover - external failure
        raise DownloadError("Failed to download audio stream.") from exc

    path = pathlib.Path(downloaded)
    filesize_bytes = None
    try:
        filesize_bytes = path.stat().st_size
    except OSError:
        filesize_bytes = None

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

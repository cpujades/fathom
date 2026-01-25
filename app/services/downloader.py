from __future__ import annotations

import pathlib
import uuid
from dataclasses import dataclass

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from app.core.errors import ExternalServiceError


class DownloadError(ExternalServiceError):
    pass


@dataclass(frozen=True)
class DownloadResult:
    path: pathlib.Path
    video_id: str | None


@dataclass(frozen=True)
class VideoMetadata:
    video_id: str | None
    duration_seconds: int | None
    title: str | None


def download_audio(url: str, output_dir: str) -> DownloadResult:
    output_path = pathlib.Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4().hex
    outtmpl = str(output_path / f"{file_id}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except YtDlpDownloadError as exc:
        raise DownloadError("Failed to download audio from the provided URL.") from exc
    except Exception as exc:
        raise DownloadError("Unexpected error while downloading audio.") from exc

    if not info:
        raise DownloadError("Failed to download audio (no metadata returned).")

    matches = sorted(output_path.glob(f"{file_id}.*"))
    if not matches:
        raise DownloadError("Download finished but the audio file was not found on disk.")

    video_id = info.get("id") if isinstance(info, dict) else None
    if not isinstance(video_id, str):
        video_id = None

    return DownloadResult(path=matches[0], video_id=video_id)


def fetch_video_metadata(url: str) -> VideoMetadata:
    ydl_opts = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except YtDlpDownloadError as exc:
        raise DownloadError("Failed to fetch video metadata.") from exc
    except Exception as exc:
        raise DownloadError("Unexpected error while fetching metadata.") from exc

    if not info:
        raise DownloadError("Failed to fetch metadata (no data returned).")

    video_id = info.get("id") if isinstance(info, dict) else None
    if not isinstance(video_id, str):
        video_id = None

    duration = info.get("duration") if isinstance(info, dict) else None
    duration_seconds = duration if isinstance(duration, int) else None

    title = info.get("title") if isinstance(info, dict) else None
    if not isinstance(title, str):
        title = None

    return VideoMetadata(video_id=video_id, duration_seconds=duration_seconds, title=title)

from __future__ import annotations

import pathlib
import uuid

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from app.core.errors import ExternalServiceError


class DownloadError(ExternalServiceError):
    pass


def download_audio(url: str, output_dir: str) -> pathlib.Path:
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

    return matches[0]

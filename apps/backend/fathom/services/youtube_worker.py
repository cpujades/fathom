"""Disposable subprocess entry point for bounded pytubefix operations."""

from __future__ import annotations

import json
import sys
from typing import NoReturn

from fathom.services.downloader import DownloadError, download_audio, fetch_video_metadata

MAX_REQUEST_BYTES = 16_000


def main() -> NoReturn:
    try:
        raw_request = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw_request) > MAX_REQUEST_BYTES:
            raise DownloadError("YouTube source request was too large.")
        request = json.loads(raw_request)
        if not isinstance(request, dict):
            raise DownloadError("YouTube source request was invalid.")

        operation = request.get("operation")
        url = request.get("url")
        if not isinstance(url, str) or not url:
            raise DownloadError("YouTube source URL was invalid.")

        if operation == "metadata":
            metadata = fetch_video_metadata(url)
            result: dict[str, object] = {
                "video_id": metadata.video_id,
                "duration_seconds": metadata.duration_seconds,
                "title": metadata.title,
            }
        elif operation == "download":
            output_dir = request.get("output_dir")
            max_bytes = request.get("max_bytes")
            deadline_seconds = request.get("deadline_seconds")
            if (
                not isinstance(output_dir, str)
                or not isinstance(max_bytes, int)
                or isinstance(max_bytes, bool)
                or not isinstance(deadline_seconds, (int, float))
                or isinstance(deadline_seconds, bool)
            ):
                raise DownloadError("YouTube download request was invalid.")
            download = download_audio(
                url,
                output_dir,
                max_bytes=max_bytes,
                deadline_seconds=float(deadline_seconds),
            )
            result = {
                "path": str(download.path),
                "video_id": download.video_id,
                "mime_type": download.mime_type,
                "subtype": download.subtype,
                "filesize_bytes": download.filesize_bytes,
                "title": download.title,
                "author": download.author,
                "description": download.description,
                "keywords": download.keywords,
                "views": download.views,
                "likes": download.likes,
                "length_seconds": download.length_seconds,
            }
        else:
            raise DownloadError("YouTube source operation was invalid.")

        _finish({"ok": True, "result": result}, exit_code=0)
    except DownloadError as exc:
        _finish({"ok": False, "detail": exc.detail}, exit_code=1)
    except Exception:
        _finish({"ok": False, "detail": "YouTube source request failed."}, exit_code=1)


def _finish(payload: dict[str, object], *, exit_code: int) -> NoReturn:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.flush()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()

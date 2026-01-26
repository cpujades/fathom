from __future__ import annotations

from urllib.parse import ParseResult, parse_qs, urlparse

from app.core.config import Settings
from app.core.errors import InvalidRequestError


def _extract_youtube_video_id(parsed_url: ParseResult) -> str | None:
    path = (parsed_url.path or "").strip("/")
    if not path:
        return None

    if parsed_url.hostname and parsed_url.hostname.lower() == "youtu.be":
        return path.split("/")[0] or None

    query = parse_qs(parsed_url.query or "")
    if path == "watch":
        value = query.get("v", [None])[0]
        return value or None

    for prefix in ("shorts/", "embed/", "live/"):
        if path.startswith(prefix):
            value = path.removeprefix(prefix).split("/")[0]
            return value or None

    return None


def validate_youtube_url(url: str, settings: Settings) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allowed_hosts = {h.lower() for h in settings.youtube_allow_hosts}

    if not host or host not in allowed_hosts:
        raise InvalidRequestError("Only YouTube URLs are allowed.")

    query = parse_qs(parsed.query or "")
    if query.get("list", [None])[0]:
        raise InvalidRequestError("Playlist URLs are not supported.")

    video_id = _extract_youtube_video_id(parsed)
    if not video_id:
        raise InvalidRequestError("Invalid YouTube video URL.")


def validate_video_duration(duration_seconds: int | None, settings: Settings) -> None:
    if duration_seconds is None:
        return
    if duration_seconds > settings.max_duration_seconds:
        raise InvalidRequestError("Video exceeds maximum allowed duration.")

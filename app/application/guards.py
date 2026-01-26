from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.core.config import Settings
from app.core.errors import InvalidRequestError
from app.services.youtube import extract_youtube_video_id


def validate_youtube_url(url: str, settings: Settings) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allowed_hosts = {h.lower() for h in settings.youtube_allow_hosts}

    if not host or host not in allowed_hosts:
        raise InvalidRequestError("Only YouTube URLs are allowed.")

    query = parse_qs(parsed.query or "")
    if query.get("list", [None])[0]:
        raise InvalidRequestError("Playlist URLs are not supported.")

    video_id = extract_youtube_video_id(parsed)
    if not video_id:
        raise InvalidRequestError("Invalid YouTube video URL.")


def validate_video_duration(duration_seconds: int | None, settings: Settings) -> None:
    if duration_seconds is None:
        return
    if duration_seconds > settings.max_duration_seconds:
        raise InvalidRequestError("Video exceeds maximum allowed duration.")

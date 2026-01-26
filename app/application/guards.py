from __future__ import annotations

from urllib.parse import urlparse

from app.core.config import Settings
from app.core.errors import InvalidRequestError


def validate_youtube_url(url: str, settings: Settings) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allowed_hosts = {h.lower() for h in settings.youtube_allow_hosts}

    if not host or host not in allowed_hosts:
        raise InvalidRequestError("Only YouTube URLs are allowed.")


def validate_video_duration(duration_seconds: int | None, settings: Settings) -> None:
    if duration_seconds is None:
        return
    if duration_seconds > settings.max_duration_seconds:
        raise InvalidRequestError("Video exceeds maximum allowed duration.")

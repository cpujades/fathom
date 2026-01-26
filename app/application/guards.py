from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.core.errors import InvalidRequestError
from app.services.youtube import extract_youtube_video_id

# ---------------------------------------------------------------------------
# Input validation constants
# ---------------------------------------------------------------------------
YOUTUBE_ALLOWED_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
        "music.youtube.com",
    }
)

MAX_VIDEO_DURATION_SECONDS = 7200  # 2 hours


def validate_youtube_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if not host or host not in YOUTUBE_ALLOWED_HOSTS:
        raise InvalidRequestError("Only YouTube URLs are allowed.")

    query = parse_qs(parsed.query or "")
    if query.get("list", [None])[0]:
        raise InvalidRequestError("Playlist URLs are not supported.")

    video_id = extract_youtube_video_id(parsed)
    if not video_id:
        raise InvalidRequestError("Invalid YouTube video URL.")


def validate_video_duration(duration_seconds: int | None) -> None:
    if duration_seconds is None:
        return
    if duration_seconds > MAX_VIDEO_DURATION_SECONDS:
        raise InvalidRequestError("Video exceeds maximum allowed duration.")

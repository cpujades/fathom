from __future__ import annotations

from urllib.parse import ParseResult, parse_qs


def extract_youtube_video_id(parsed_url: ParseResult) -> str | None:
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

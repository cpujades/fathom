from __future__ import annotations

import time
import uuid
from collections import deque

from fastapi import Request
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from fathom.core.errors import RateLimitError, RequestTooLargeError
from fathom.core.logging import log_context

# ---------------------------------------------------------------------------
# Request size limits
# ---------------------------------------------------------------------------
MAX_REQUEST_BYTES = 64_000  # 64 KB

# ---------------------------------------------------------------------------
# Rate limiting defaults (only used when rate limiting is enabled)
# ---------------------------------------------------------------------------
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_IPS = 10_000
RATE_LIMIT_IDLE_SECONDS = 1800  # 30 minutes

_rate_limit_buckets: dict[str, deque[float]] = {}
_rate_limit_last_seen: dict[str, float] = {}


async def _enforce_request_size(request: Request) -> None:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BYTES:
                raise RequestTooLargeError("Request body too large.")
        except ValueError:
            pass

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_REQUEST_BYTES:
            raise RequestTooLargeError("Request body too large.")

    request._body = bytes(body)


def _evict_stale_buckets(now: float) -> None:
    stale_ips = [ip for ip, last in _rate_limit_last_seen.items() if now - last > RATE_LIMIT_IDLE_SECONDS]
    for ip in stale_ips:
        _rate_limit_last_seen.pop(ip, None)
        _rate_limit_buckets.pop(ip, None)

    if len(_rate_limit_buckets) > RATE_LIMIT_MAX_IPS:
        candidates = sorted(_rate_limit_last_seen.items(), key=lambda item: item[1])
        overflow = len(_rate_limit_buckets) - RATE_LIMIT_MAX_IPS
        for ip, _ in candidates[:overflow]:
            _rate_limit_last_seen.pop(ip, None)
            _rate_limit_buckets.pop(ip, None)


def _enforce_rate_limit(request: Request, rate_limit: int) -> None:
    forwarded_for = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    client_host = request.client.host if request.client else ""
    ip = forwarded_for or client_host or "unknown"
    now = time.monotonic()

    _evict_stale_buckets(now)

    bucket = _rate_limit_buckets.setdefault(ip, deque())
    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= rate_limit:
        raise RateLimitError("Too many requests.")

    bucket.append(now)
    _rate_limit_last_seen[ip] = now


async def log_requests(request: Request, call_next: RequestResponseEndpoint) -> Response:
    request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
    request.state.request_id = request_id

    await _enforce_request_size(request)

    rate_limit = getattr(request.app.state, "rate_limit", 0)
    if rate_limit > 0:
        _enforce_rate_limit(request, rate_limit)

    with log_context(request_id=request_id, method=request.method, path=request.url.path):
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

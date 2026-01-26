from __future__ import annotations

import logging
import time
import uuid
from collections import deque

from fastapi import Request
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.core.errors import RateLimitError, RequestTooLargeError

logger = logging.getLogger("fathom")
_rate_limit_buckets: dict[str, deque[float]] = {}


async def _enforce_request_size(request: Request, max_bytes: int) -> None:
    if max_bytes <= 0:
        return

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise RequestTooLargeError("Request body too large.")
        except ValueError:
            # Ignore invalid Content-Length and fall back to streaming enforcement.
            pass

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise RequestTooLargeError("Request body too large.")

    request._body = bytes(body)


async def log_requests(request: Request, call_next: RequestResponseEndpoint) -> Response:
    start = time.perf_counter()
    request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
    request.state.request_id = request_id

    await _enforce_request_size(request, request.app.state.settings.max_request_bytes)

    rate_limit = request.app.state.settings.rate_limit_requests
    if rate_limit > 0:
        window_seconds = max(request.app.state.settings.rate_limit_window_seconds, 1)
        forwarded_for = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        client_host = request.client.host if request.client else ""
        ip = forwarded_for or client_host or "unknown"
        now = time.monotonic()
        bucket = _rate_limit_buckets.setdefault(ip, deque())
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= rate_limit:
            raise RateLimitError("Too many requests.")
        bucket.append(now)

    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s %s %.2fms request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
    )
    return response

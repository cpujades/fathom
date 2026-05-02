from __future__ import annotations

import uuid

from fastapi import Request
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from fathom.core.errors import RequestTooLargeError
from fathom.core.logging import log_context
from fathom.core.rate_limits import maybe_enforce_rate_limit

# ---------------------------------------------------------------------------
# Request size limits
# ---------------------------------------------------------------------------
MAX_REQUEST_BYTES = 64_000  # 64 KB


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


async def log_requests(request: Request, call_next: RequestResponseEndpoint) -> Response:
    request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
    request.state.request_id = request_id

    await _enforce_request_size(request)

    rate_limit = getattr(request.app.state, "rate_limit", 0)
    if rate_limit > 0:
        await maybe_enforce_rate_limit(request, rate_limit)

    with log_context(request_id=request_id, method=request.method, path=request.url.path):
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

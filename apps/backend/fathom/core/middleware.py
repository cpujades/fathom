from __future__ import annotations

import logging
import time
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
logger = logging.getLogger(__name__)


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
    started_at = time.perf_counter()

    await _enforce_request_size(request)

    rate_limit = getattr(request.app.state, "rate_limit", 0)
    if rate_limit > 0:
        await maybe_enforce_rate_limit(request, rate_limit)

    with log_context(request_id=request_id, method=request.method, path=request.url.path):
        response: Response | None = None
        try:
            response = await call_next(request)
            response.headers["X-Request-Id"] = request_id
            return response
        except Exception:
            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.exception(
                "request.failed",
                extra={
                    "status_code": 500,
                    "duration_ms": round(duration_ms, 2),
                    "error_type": "UnhandledException",
                    "user_id": getattr(request.state, "user_id", None),
                },
            )
            raise
        finally:
            if response is not None:
                status_code = response.status_code
                duration_ms = (time.perf_counter() - started_at) * 1000
                if status_code >= 500:
                    log_level = logging.ERROR
                elif status_code >= 400:
                    log_level = logging.WARNING
                else:
                    log_level = logging.INFO
                logger.log(
                    log_level,
                    "request.completed",
                    extra={
                        "status_code": status_code,
                        "duration_ms": round(duration_ms, 2),
                        "user_id": getattr(request.state, "user_id", None),
                        "error_code": getattr(request.state, "error_code", None),
                        "error_type": getattr(request.state, "error_type", None),
                    },
                )

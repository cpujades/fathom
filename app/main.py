from __future__ import annotations

import logging
import time
import uuid
from collections import deque

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.api.router import router
from app.core.config import get_settings
from app.core.errors import AppError, RateLimitError, RequestTooLargeError
from app.core.logging import setup_logging

load_dotenv()
setup_logging()
settings = get_settings()
logger = logging.getLogger("fathom")

middleware: list[Middleware] = []
if settings.cors_allow_origins:
    middleware.append(
        Middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    )

app = FastAPI(title="Fathom MVP", middleware=middleware)
app.include_router(router)

_rate_limit_buckets: dict[str, deque[float]] = {}


@app.middleware("http")
async def log_requests(request: Request, call_next: RequestResponseEndpoint) -> Response:
    start = time.perf_counter()
    request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
    request.state.request_id = request_id

    max_bytes = settings.max_request_bytes
    if max_bytes > 0:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > max_bytes:
            raise RequestTooLargeError("Request body too large.")

    rate_limit = settings.rate_limit_requests
    if rate_limit > 0:
        window_seconds = max(settings.rate_limit_window_seconds, 1)
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


@app.exception_handler(AppError)
async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.detail}},
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "invalid_request", "message": "Invalid request"}},
    )

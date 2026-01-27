from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import AppError
from app.core.logging import log_context

logger = logging.getLogger(__name__)


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    request.state.error_code = exc.code
    request.state.error_status_code = exc.status_code
    # Log only server-side failures here. Client errors should be logged at the source.
    if exc.status_code >= 500:
        with log_context(request_id=request_id, method=request.method, path=request.url.path):
            logger.error(
                "%s",
                exc.detail,
                extra={
                    "error_code": exc.code,
                    "status_code": exc.status_code,
                    "error_type": type(exc).__name__,
                },
            )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.detail}},
    )


async def handle_validation_error(request: Request, _exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    request.state.error_code = "invalid_request"
    request.state.error_status_code = 400
    with log_context(request_id=request_id, method=request.method, path=request.url.path):
        logger.warning("Invalid request", extra={"error_code": "invalid_request", "status_code": 400})
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "invalid_request", "message": "Invalid request"}},
    )

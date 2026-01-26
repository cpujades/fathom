from __future__ import annotations

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
from app.core.errors import AppError
from app.core.handlers import handle_app_error, handle_validation_error
from app.core.logging import setup_logging
from app.core.middleware import log_requests

load_dotenv()
setup_logging()
settings = get_settings()

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
app.state.settings = settings


@app.middleware("http")
async def log_requests_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    return await log_requests(request, call_next)


@app.exception_handler(AppError)
async def handle_app_error_wrapper(request: Request, exc: AppError) -> JSONResponse:
    return await handle_app_error(request, exc)


@app.exception_handler(RequestValidationError)
async def handle_validation_error_wrapper(request: Request, exc: RequestValidationError) -> JSONResponse:
    return await handle_validation_error(request, exc)

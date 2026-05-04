from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from fathom.api import __version__
from fathom.api.routers import (
    billing_router,
    briefing_sessions_router,
    briefings_router,
    meta_router,
    webhooks_router,
)
from fathom.core.config import Settings, get_settings
from fathom.core.errors import AppError
from fathom.core.handlers import handle_app_error, handle_validation_error
from fathom.core.lifespan import lifespan
from fathom.core.logging import setup_logging
from fathom.core.middleware import log_requests


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    Application factory for creating FastAPI instances.

    Args:
        settings: Optional settings override. If None, loads from environment.
                  Useful for testing with custom configuration.
    """
    if settings is None:
        settings = get_settings()

    middleware: list[Middleware] = []
    if settings.cors_allow_origins:
        middleware.append(
            Middleware(
                cast(Any, CORSMiddleware),
                allow_origins=settings.cors_allow_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        )

    app = FastAPI(
        title="Talven",
        description="Talven briefing service",
        version=__version__,
        middleware=middleware,
        lifespan=lifespan,
    )
    app.include_router(meta_router)
    app.include_router(briefing_sessions_router)
    app.include_router(briefings_router)
    app.include_router(billing_router)
    app.include_router(webhooks_router)
    app.state.settings = settings
    app.state.rate_limit = settings.rate_limit
    app.state.trust_proxy_headers = settings.trust_proxy_headers

    # Starlette's middleware typing is stricter than the runtime API here.
    app.add_middleware(cast(Any, BaseHTTPMiddleware), dispatch=log_requests)
    app.add_exception_handler(AppError, cast(Any, handle_app_error))
    app.add_exception_handler(RequestValidationError, cast(Any, handle_validation_error))

    return app


# Initialize logging once at module load
setup_logging(service="api")

# Default app instance for uvicorn (uvicorn --app-dir apps/backend fathom.api.app:app)
app = create_app()

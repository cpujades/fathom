from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from fathom.api import __version__
from fathom.api.routers import jobs_router, meta_router, summaries_router
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
                CORSMiddleware,
                allow_origins=settings.cors_allow_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        )

    app = FastAPI(
        title="Fathom",
        description="Podcast chatbot service",
        version=__version__,
        middleware=middleware,
        lifespan=lifespan,
    )
    app.include_router(meta_router)
    app.include_router(jobs_router)
    app.include_router(summaries_router)
    app.state.settings = settings
    app.state.rate_limit = settings.rate_limit

    app.add_middleware(BaseHTTPMiddleware, dispatch=log_requests)
    app.add_exception_handler(AppError, handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, handle_validation_error)  # type: ignore[arg-type]

    return app


# Initialize logging once at module load
setup_logging()

# Default app instance for uvicorn (uvicorn --app-dir apps/backend fathom.api.app:app)
app = create_app()

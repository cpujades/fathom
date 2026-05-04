from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fathom.core.config import get_settings
from fathom.services.supabase import create_postgres_pool

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info(
        "api.started",
        extra={
            "app_env": settings.app_env,
            "rate_limit_enabled": settings.rate_limit > 0,
            "trust_proxy_headers": settings.trust_proxy_headers,
        },
    )
    postgres_pool = None
    if settings.rate_limit > 0:
        postgres_pool = await create_postgres_pool(settings)
        app.state.postgres_pool = postgres_pool
        logger.info("api.postgres_pool.initialized", extra={"purpose": "rate_limiting"})

    try:
        logger.info("api.ready")
        yield
    finally:
        if postgres_pool is not None:
            await postgres_pool.close()
            logger.info("api.postgres_pool.closed", extra={"purpose": "rate_limiting"})
        logger.info("api.stopped")

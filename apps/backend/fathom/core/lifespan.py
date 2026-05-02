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
        "API environment resolved. app_env=%s supabase_url=%s",
        settings.app_env,
        settings.supabase_url,
    )
    postgres_pool = None
    if settings.rate_limit > 0:
        postgres_pool = await create_postgres_pool(settings)
        app.state.postgres_pool = postgres_pool
        logger.info("shared Postgres pool initialized for API rate limiting")

    try:
        yield
    finally:
        if postgres_pool is not None:
            await postgres_pool.close()
            logger.info("shared Postgres pool closed")

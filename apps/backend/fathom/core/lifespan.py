from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fathom.application.briefings.sessions.event_coordinator import JobEventCoordinator
from fathom.core.config import Settings
from fathom.services.supabase import (
    create_postgres_pool,
    create_supabase_admin_client,
    managed_supabase_client,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
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
        async with managed_supabase_client(await create_supabase_admin_client(settings)) as event_client:
            event_coordinator = JobEventCoordinator(settings, event_client)
            app.state.job_event_coordinator = event_coordinator
            await event_coordinator.start()
            try:
                logger.info("api.ready")
                yield
            finally:
                await event_coordinator.close()
    finally:
        if postgres_pool is not None:
            await postgres_pool.close()
            logger.info("api.postgres_pool.closed", extra={"purpose": "rate_limiting"})
        logger.info("api.stopped")

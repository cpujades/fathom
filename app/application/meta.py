from __future__ import annotations

import logging
import time

from postgrest import APIError

from app import __version__
from app.core.config import Settings
from app.core.errors import NotReadyError
from app.schemas.meta import HealthResponse, ReadyResponse, StatusResponse
from app.services.supabase import create_supabase_admin_client

_START_TIME = time.monotonic()

logger = logging.getLogger(__name__)


async def health_status() -> HealthResponse:
    logger.info("health check ok")
    return HealthResponse(status="ok")


async def readiness_status(settings: Settings) -> ReadyResponse:
    # Minimal readiness checks: configuration present + Supabase reachable.
    if not settings.supabase_url or not settings.supabase_publishable_key or not settings.supabase_secret_key:
        logger.warning("readiness check failed: supabase not configured")
        raise NotReadyError("Supabase is not configured.")

    client = await create_supabase_admin_client(settings)
    # Lightweight query to ensure PostgREST is reachable.
    try:
        await client.table("jobs").select("id").limit(1).execute()
    except APIError as exc:
        logger.warning(
            "readiness check failed: supabase not reachable",
            extra={"error_type": type(exc).__name__},
        )
        raise NotReadyError("Supabase is not reachable.") from exc

    logger.info("readiness check ok")
    return ReadyResponse(status="ok")


async def status_snapshot() -> StatusResponse:
    uptime_seconds = time.monotonic() - _START_TIME
    logger.info("status snapshot", extra={"uptime_seconds": round(uptime_seconds, 2), "version": __version__})
    return StatusResponse(
        status="ok",
        version=__version__,
        uptime_seconds=uptime_seconds,
    )

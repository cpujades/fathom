from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from postgrest import APIError

from fathom.api import __version__
from fathom.core.config import Settings
from fathom.core.errors import ConfigurationError, NotReadyError
from fathom.schemas.meta import HealthResponse, ReadyResponse, StatusResponse
from fathom.services import polar
from fathom.services.supabase import create_postgres_connection, create_supabase_admin_client

_START_TIME = time.monotonic()

logger = logging.getLogger(__name__)


async def health_status() -> HealthResponse:
    logger.info("api.health.ok")
    return HealthResponse(status="ok")


def _is_strict_runtime_env(settings: Settings) -> bool:
    return (settings.app_env or "local").strip().lower() not in {"local", "test"}


def _require_supabase_config(settings: Settings) -> None:
    if settings.supabase_url and settings.supabase_publishable_key and settings.supabase_secret_key:
        return
    raise NotReadyError("Supabase is not configured.")


def _require_billing_config(settings: Settings) -> None:
    try:
        polar.get_polar_access_token(settings)
        polar.get_polar_webhook_secret(settings)
        polar.get_polar_success_url(settings)
        polar.get_polar_portal_return_url(settings)
    except ConfigurationError as exc:
        raise NotReadyError(f"Billing is not configured: {exc.detail}") from exc


@asynccontextmanager
async def _postgres_connection(settings: Settings):
    async with create_postgres_connection(settings) as conn:
        yield conn


async def _check_postgrest(settings: Settings) -> None:
    try:
        client = await create_supabase_admin_client(settings)
        await client.table("jobs").select("id").limit(1).execute()
    except APIError as exc:
        logger.warning(
            "api.ready.failed",
            extra={"dependency": "supabase", "error_type": type(exc).__name__},
        )
        raise NotReadyError("Supabase is not reachable.") from exc


async def _check_postgres(settings: Settings) -> None:
    try:
        async with _postgres_connection(settings) as conn:
            await conn.fetchval("select 1")
    except ConfigurationError as exc:
        logger.warning("api.ready.failed", extra={"dependency": "postgres", "error_type": type(exc).__name__})
        raise NotReadyError(f"Direct Postgres is not configured: {exc.detail}") from exc
    except Exception as exc:
        logger.warning("api.ready.failed", extra={"dependency": "postgres", "error_type": type(exc).__name__})
        raise NotReadyError("Direct Postgres is not reachable.") from exc


async def readiness_status(settings: Settings) -> ReadyResponse:
    _require_supabase_config(settings)

    await _check_postgrest(settings)
    await _check_postgres(settings)

    if _is_strict_runtime_env(settings):
        _require_billing_config(settings)

    logger.info("api.ready.ok")
    return ReadyResponse(status="ok")


async def status_snapshot() -> StatusResponse:
    uptime_seconds = time.monotonic() - _START_TIME
    logger.info("api.status.snapshot", extra={"uptime_seconds": round(uptime_seconds, 2), "version": __version__})
    return StatusResponse(
        status="ok",
        version=__version__,
        uptime_seconds=uptime_seconds,
    )

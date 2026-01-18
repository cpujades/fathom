from __future__ import annotations

import time
from importlib.metadata import PackageNotFoundError, version

from app.core.config import Settings
from app.core.errors import NotReadyError
from app.schemas.meta import HealthResponse, ReadyResponse, StatusResponse
from app.services.supabase import create_supabase_admin_client

_START_TIME = time.monotonic()


async def health_status() -> HealthResponse:
    return HealthResponse(status="ok")


async def readiness_status(settings: Settings) -> ReadyResponse:
    # Minimal readiness checks: configuration present + Supabase reachable.
    if not settings.supabase_url or not settings.supabase_publishable_key or not settings.supabase_secret_key:
        raise NotReadyError("Supabase is not configured.")

    client = await create_supabase_admin_client(settings)
    # Lightweight query to ensure PostgREST is reachable.
    try:
        await client.table("jobs").select("id").limit(1).execute()
    except Exception as exc:
        raise NotReadyError("Supabase is not reachable.") from exc

    return ReadyResponse(status="ok")


async def status_snapshot() -> StatusResponse:
    try:
        app_version = version("fathom")
    except PackageNotFoundError:
        app_version = None

    return StatusResponse(
        status="ok",
        version=app_version,
        uptime_seconds=time.monotonic() - _START_TIME,
    )

from __future__ import annotations

import time
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.errors import NotReadyError
from app.schemas.meta import HealthResponse, ReadyResponse, StatusResponse
from app.services.supabase import create_supabase_admin_client

router = APIRouter(prefix="/meta")

_START_TIME = time.monotonic()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
def ready(settings: Annotated[Settings, Depends(get_settings)]) -> ReadyResponse:
    # Minimal readiness checks: configuration present + Supabase reachable.
    if not settings.supabase_url or not settings.supabase_publishable_key or not settings.supabase_secret_key:
        raise NotReadyError("Supabase is not configured.")

    client = create_supabase_admin_client(settings)
    # Lightweight query to ensure PostgREST is reachable.
    try:
        client.table("jobs").select("id").limit(1).execute()
    except Exception as exc:
        raise NotReadyError("Supabase is not reachable.") from exc

    return ReadyResponse(status="ok")


@router.get("/status", response_model=StatusResponse)
def status() -> StatusResponse:
    try:
        app_version = version("fathom")
    except PackageNotFoundError:
        app_version = None

    return StatusResponse(
        status="ok",
        version=app_version,
        uptime_seconds=time.monotonic() - _START_TIME,
    )

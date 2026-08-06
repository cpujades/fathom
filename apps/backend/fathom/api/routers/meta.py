from typing import Annotated

from fastapi import APIRouter, Depends, Request

from fathom.application.meta import health_status, readiness_status, status_snapshot
from fathom.core.config import Settings, get_settings
from fathom.schemas.meta import HealthResponse, ReadyResponse, StatusResponse

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return await health_status()


@router.get("/ready", response_model=ReadyResponse)
async def ready(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> ReadyResponse:
    return await readiness_status(settings, getattr(request.app.state, "job_event_coordinator", None))


@router.get("/status", response_model=StatusResponse)
async def status(request: Request) -> StatusResponse:
    return await status_snapshot(getattr(request.app.state, "job_event_coordinator", None))

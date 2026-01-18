from typing import Annotated

from fastapi import APIRouter, Depends

from app.application.meta import health_status, readiness_status, status_snapshot
from app.core.config import Settings, get_settings
from app.schemas.meta import HealthResponse, ReadyResponse, StatusResponse

router = APIRouter(prefix="/meta")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return await health_status()


@router.get("/ready", response_model=ReadyResponse)
async def ready(settings: Annotated[Settings, Depends(get_settings)]) -> ReadyResponse:
    return await readiness_status(settings)


@router.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    return await status_snapshot()

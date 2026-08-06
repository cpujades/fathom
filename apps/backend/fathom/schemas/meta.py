from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    event_delivery: Literal["healthy", "degraded"]


class StatusResponse(BaseModel):
    status: str
    version: str | None = None
    uptime_seconds: float | None = None
    event_delivery: Literal["healthy", "degraded"]

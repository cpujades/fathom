from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str


class StatusResponse(BaseModel):
    status: str
    version: str | None = None
    uptime_seconds: float | None = None

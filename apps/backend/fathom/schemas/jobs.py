from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

JobStatus = Literal["queued", "running", "succeeded", "failed"]


class JobStatusResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    summary_id: UUID | None = None
    error_code: str | None = None
    error_message: str | None = None
    stage: str | None = None
    progress: int | None = None
    status_message: str | None = None

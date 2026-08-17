from pydantic import BaseModel, Field


class ErrorDetails(BaseModel):
    required_seconds: int | None = Field(default=None, ge=0)
    available_seconds: int | None = Field(default=None, ge=0)
    debt_seconds: int | None = Field(default=None, ge=0)
    maximum_seconds: int | None = Field(default=None, ge=0)
    pending_seconds: int | None = Field(default=None, ge=0)
    active_job_count: int | None = Field(default=None, ge=0)
    maximum_active_jobs: int | None = Field(default=None, ge=1)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: ErrorDetails | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail

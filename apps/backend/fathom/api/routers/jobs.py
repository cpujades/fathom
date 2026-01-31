from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from fathom.api.deps.auth import AuthContext, get_auth_context
from fathom.application.jobs import get_job_status
from fathom.core.config import Settings, get_settings
from fathom.schemas.errors import ErrorResponse
from fathom.schemas.jobs import JobStatusResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        400: {"model": ErrorResponse, "description": "Invalid job id."},
        404: {"model": ErrorResponse, "description": "Job not found."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def get_job(
    job_id: UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JobStatusResponse:
    return await get_job_status(job_id, auth, settings)

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps.auth import AuthContext, get_auth_context
from app.core.config import get_settings
from app.schemas.errors import ErrorResponse
from app.schemas.jobs import JobStatusResponse
from app.services.supabase import create_supabase_user_client, fetch_job

router = APIRouter(prefix="/jobs")


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
def get_job(
    job_id: UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> JobStatusResponse:
    settings = get_settings()
    client = create_supabase_user_client(settings, auth.access_token)
    job = fetch_job(client, str(job_id))

    return JobStatusResponse(
        job_id=job["id"],
        status=job["status"],
        summary_id=job.get("summary_id"),
        error_code=job.get("error_code"),
        error_message=job.get("error_message"),
    )

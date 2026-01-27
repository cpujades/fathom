from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from starlette.responses import StreamingResponse

from app.api.deps.auth import AuthContext, get_auth_context
from app.application.jobs import JOB_STATUS_POLL_INTERVAL_SECONDS, get_job_status, stream_job_events
from app.core.config import Settings, get_settings
from app.schemas.errors import ErrorResponse
from app.schemas.jobs import JobStatusResponse

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


@router.get(
    "/{job_id}/events",
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        400: {"model": ErrorResponse, "description": "Invalid job id."},
        404: {"model": ErrorResponse, "description": "Job not found."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def server_sent_events(
    job_id: UUID,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(
        stream_job_events(
            job_id,
            request,
            auth,
            settings,
            poll_interval_seconds=JOB_STATUS_POLL_INTERVAL_SECONDS,
        ),
        media_type="text/event-stream",
        headers=headers,
    )

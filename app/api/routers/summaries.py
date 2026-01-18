from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps.auth import AuthContext, get_auth_context
from app.application.summaries import create_summary_job, get_summary_with_pdf
from app.core.config import Settings, get_settings
from app.schemas.errors import ErrorResponse
from app.schemas.summaries import SummarizeRequest, SummarizeResponse, SummaryResponse

router = APIRouter()


@router.post(
    "/summarize",
    response_model=SummarizeResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        400: {"model": ErrorResponse, "description": "Invalid input (e.g., malformed URL)."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def summarize(
    request: SummarizeRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SummarizeResponse:
    return await create_summary_job(request, auth, settings)


@router.get(
    "/summaries/{summary_id}",
    response_model=SummaryResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        400: {"model": ErrorResponse, "description": "Invalid summary id."},
        404: {"model": ErrorResponse, "description": "Summary not found."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def get_summary(
    summary_id: UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SummaryResponse:
    return await get_summary_with_pdf(summary_id, auth, settings)

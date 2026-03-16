from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from fathom.api.deps.auth import AuthContext, get_auth_context
from fathom.application.briefings import create_briefing_pdf, get_briefing
from fathom.core.config import Settings, get_settings
from fathom.schemas.briefings import BriefingPdfResponse, BriefingResponse
from fathom.schemas.errors import ErrorResponse

router = APIRouter(prefix="/briefings", tags=["briefings"])


@router.get(
    "/{briefing_id}",
    response_model=BriefingResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        400: {"model": ErrorResponse, "description": "Invalid briefing id."},
        404: {"model": ErrorResponse, "description": "Briefing not found."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def get_briefing_by_id(
    briefing_id: UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BriefingResponse:
    return await get_briefing(briefing_id, auth, settings)


@router.post(
    "/{briefing_id}/pdf",
    response_model=BriefingPdfResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        400: {"model": ErrorResponse, "description": "Invalid briefing id."},
        404: {"model": ErrorResponse, "description": "Briefing not found."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def generate_briefing_pdf(
    briefing_id: UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BriefingPdfResponse:
    return await create_briefing_pdf(briefing_id, auth, settings)

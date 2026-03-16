from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from starlette.responses import Response, StreamingResponse

from fathom.api.deps.auth import AuthContext, get_auth_context
from fathom.application.briefing_sessions import (
    create_briefing_session,
    delete_briefing_session,
    get_briefing_session,
    stream_briefing_session_events,
)
from fathom.core.config import Settings, get_settings
from fathom.schemas.briefing_sessions import BriefingSessionCreateRequest, BriefingSessionResponse
from fathom.schemas.errors import ErrorResponse

router = APIRouter(prefix="/briefing-sessions", tags=["briefing sessions"])


@router.post(
    "",
    response_model=BriefingSessionResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        400: {"model": ErrorResponse, "description": "Invalid input (e.g., malformed URL)."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def create_session(
    request: BriefingSessionCreateRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BriefingSessionResponse:
    return await create_briefing_session(request, auth, settings)


@router.get(
    "/{session_id}",
    response_model=BriefingSessionResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        400: {"model": ErrorResponse, "description": "Invalid session id."},
        404: {"model": ErrorResponse, "description": "Session not found."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def get_session(
    session_id: UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BriefingSessionResponse:
    return await get_briefing_session(session_id, auth, settings)


@router.get(
    "/{session_id}/events",
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        400: {"model": ErrorResponse, "description": "Invalid session id."},
        404: {"model": ErrorResponse, "description": "Session not found."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def get_session_events(
    session_id: UUID,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    return await stream_briefing_session_events(session_id, auth, settings, request)


@router.delete(
    "/{session_id}",
    status_code=204,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        400: {"model": ErrorResponse, "description": "Invalid session id."},
        404: {"model": ErrorResponse, "description": "Session not found."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
    },
)
async def delete_session(
    session_id: UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    await delete_briefing_session(session_id, auth, settings)
    return Response(status_code=204)

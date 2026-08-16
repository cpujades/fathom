from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from starlette.responses import Response, StreamingResponse

from fathom.api.deps.auth import get_auth_context
from fathom.application.briefings.sessions import (
    create_briefing_session,
    delete_briefing_session,
    get_briefing_session,
    stream_briefing_session_events,
)
from fathom.application.identity import AuthenticatedUser
from fathom.core.config import Settings, get_settings
from fathom.core.rate_limits import get_request_client_ip
from fathom.schemas.briefing_sessions import BriefingSessionCreateRequest, BriefingSessionResponse
from fathom.schemas.errors import ErrorResponse

router = APIRouter(prefix="/briefing-sessions", tags=["briefing sessions"])


@router.post(
    "",
    response_model=BriefingSessionResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        400: {"model": ErrorResponse, "description": "Invalid input (e.g., malformed URL)."},
        409: {"model": ErrorResponse, "description": "Current jobs or committed video time prevent admission."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def create_session(
    request: BriefingSessionCreateRequest,
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
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
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
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
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    event_stream = await stream_briefing_session_events(
        session_id,
        auth,
        settings,
        client_subject=f"ip:{get_request_client_ip(request)}",
        last_event_id=request.headers.get("last-event-id"),
        is_disconnected=request.is_disconnected,
        event_coordinator=getattr(request.app.state, "job_event_coordinator", None),
    )
    return StreamingResponse(
        event_stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    await delete_briefing_session(session_id, auth, settings)
    return Response(status_code=204)

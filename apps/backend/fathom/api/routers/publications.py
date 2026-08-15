from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from pydantic import HttpUrl

from fathom.api.deps.auth import get_auth_context
from fathom.application.identity import AuthenticatedUser
from fathom.application.publications import (
    get_owner_publication,
    get_public_briefing,
    get_publication_library_entries,
    get_publication_library_entry,
    list_explore_briefings,
    match_listed_publication,
    save_public_briefing,
    set_owner_publication,
)
from fathom.core.config import Settings, get_settings
from fathom.schemas.errors import ErrorResponse
from fathom.schemas.publications import (
    ExploreBriefingResponse,
    PublicationLibraryEntriesRequest,
    PublicationLibraryEntriesResponse,
    PublicationLibraryEntryResponse,
    PublicationSourceMatchResponse,
    PublicationStateResponse,
    PublicationUpdateRequest,
    PublicBriefingResponse,
)

router = APIRouter(tags=["publications"])

PUBLIC_SLUG = Path(min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")


@router.get(
    "/explore",
    response_model=ExploreBriefingResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Invalid query parameters."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def explore(
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=100)] = 24,
    offset: Annotated[int, Query(ge=0)] = 0,
    topic: Annotated[str | None, Query(min_length=1, max_length=48)] = None,
) -> ExploreBriefingResponse:
    return await list_explore_briefings(
        settings=settings,
        limit=limit,
        offset=offset,
        topic=topic,
    )


@router.get(
    "/publications/source-match",
    response_model=PublicationSourceMatchResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid source URL."},
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def match_publication_source(
    source_url: Annotated[HttpUrl, Query(alias="url")],
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PublicationSourceMatchResponse:
    return await match_listed_publication(str(source_url), auth, settings)


@router.post(
    "/publications/library-entries",
    response_model=PublicationLibraryEntriesResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        422: {"model": ErrorResponse, "description": "Invalid public slugs."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def read_publication_library_entries(
    request: PublicationLibraryEntriesRequest,
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PublicationLibraryEntriesResponse:
    return await get_publication_library_entries(request.public_slugs, auth, settings)


@router.get(
    "/publications/{public_slug}",
    response_model=PublicBriefingResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Public briefing not found."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def read_publication(
    public_slug: Annotated[str, PUBLIC_SLUG],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PublicBriefingResponse:
    return await get_public_briefing(public_slug, settings)


@router.get(
    "/publications/{public_slug}/library-entry",
    response_model=PublicationLibraryEntryResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        404: {"model": ErrorResponse, "description": "Public briefing not found."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def read_publication_library_entry(
    public_slug: Annotated[str, PUBLIC_SLUG],
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PublicationLibraryEntryResponse:
    return await get_publication_library_entry(public_slug, auth, settings)


@router.post(
    "/publications/{public_slug}/save",
    response_model=PublicationLibraryEntryResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        404: {"model": ErrorResponse, "description": "Public briefing not found."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def save_publication_to_library(
    public_slug: Annotated[str, PUBLIC_SLUG],
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PublicationLibraryEntryResponse:
    return await save_public_briefing(public_slug, auth, settings)


@router.get(
    "/briefing-sessions/{session_id}/publication",
    response_model=PublicationStateResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        404: {"model": ErrorResponse, "description": "Briefing not found."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def read_owner_publication(
    session_id: UUID,
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PublicationStateResponse:
    return await get_owner_publication(session_id, auth, settings)


@router.post(
    "/briefing-sessions/{session_id}/publication",
    response_model=PublicationStateResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid publication state."},
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        403: {"model": ErrorResponse, "description": "Publication action is not allowed."},
        409: {"model": ErrorResponse, "description": "The source is already listed in Explore."},
        404: {"model": ErrorResponse, "description": "Briefing not found."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def update_owner_publication(
    session_id: UUID,
    request: PublicationUpdateRequest,
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PublicationStateResponse:
    return await set_owner_publication(session_id, request, auth, settings)

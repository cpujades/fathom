from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps.auth import AuthContext, get_auth_context
from app.core.config import get_settings
from app.schemas.errors import ErrorResponse
from app.schemas.summaries import SummarizeRequest, SummarizeResponse, SummaryResponse
from app.services.supabase import (
    create_job,
    create_pdf_signed_url,
    create_supabase_admin_client,
    create_supabase_user_client,
    fetch_summary,
)

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
def summarize(
    request: SummarizeRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> SummarizeResponse:
    settings = get_settings()
    client = create_supabase_user_client(settings, auth.access_token)
    job = create_job(client, url=str(request.url), user_id=auth.user_id)

    return SummarizeResponse(job_id=job["id"])


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
def get_summary(
    summary_id: UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> SummaryResponse:
    settings = get_settings()
    user_client = create_supabase_user_client(settings, auth.access_token)
    summary = fetch_summary(user_client, str(summary_id))
    admin_client = create_supabase_admin_client(settings)
    pdf_url = create_pdf_signed_url(
        admin_client,
        settings.supabase_bucket,
        summary.get("pdf_object_key"),
        settings.supabase_signed_url_ttl_seconds,
    )

    return SummaryResponse(
        summary_id=summary["id"],
        markdown=summary["summary_markdown"],
        pdf_url=pdf_url,
    )

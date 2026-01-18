from __future__ import annotations

from uuid import UUID

from app.api.deps.auth import AuthContext
from app.core.config import Settings
from app.schemas.summaries import SummarizeRequest, SummarizeResponse, SummaryResponse
from app.services.supabase import (
    create_job,
    create_pdf_signed_url,
    create_supabase_admin_client,
    create_supabase_user_client,
    fetch_summary,
)


async def create_summary_job(
    request: SummarizeRequest,
    auth: AuthContext,
    settings: Settings,
) -> SummarizeResponse:
    client = await create_supabase_user_client(settings, auth.access_token)
    job = await create_job(client, url=str(request.url), user_id=auth.user_id)

    return SummarizeResponse(job_id=job["id"])


async def get_summary_with_pdf(
    summary_id: UUID,
    auth: AuthContext,
    settings: Settings,
) -> SummaryResponse:
    user_client = await create_supabase_user_client(settings, auth.access_token)
    summary = await fetch_summary(user_client, str(summary_id))
    admin_client = await create_supabase_admin_client(settings)
    pdf_url = await create_pdf_signed_url(
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

from __future__ import annotations

import asyncio
from uuid import UUID

from app.api.deps.auth import AuthContext
from app.application.guards import validate_video_duration, validate_youtube_url
from app.core.config import Settings
from app.core.constants import SIGNED_URL_TTL_SECONDS
from app.core.errors import ExternalServiceError
from app.crud.supabase.jobs import create_job
from app.crud.supabase.storage_objects import create_pdf_signed_url, upload_pdf
from app.crud.supabase.summaries import fetch_summary, update_summary_pdf_key
from app.crud.supabase.transcripts import fetch_transcript_by_id
from app.schemas.summaries import SummarizeRequest, SummarizeResponse, SummaryPdfResponse, SummaryResponse
from app.services.downloader import fetch_video_metadata
from app.services.pdf import markdown_to_pdf_bytes
from app.services.supabase import create_supabase_admin_client, create_supabase_user_client


async def create_summary_job(
    request: SummarizeRequest,
    auth: AuthContext,
    settings: Settings,
) -> SummarizeResponse:
    validate_youtube_url(str(request.url))
    metadata = await asyncio.to_thread(fetch_video_metadata, str(request.url))
    validate_video_duration(metadata.duration_seconds)

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
    object_key = summary.get("pdf_object_key")
    if not isinstance(object_key, str) or not object_key:
        return SummaryResponse(
            summary_id=summary["id"],
            markdown=summary["summary_markdown"],
            pdf_url=None,
        )

    admin_client = await create_supabase_admin_client(settings)
    pdf_url = await create_pdf_signed_url(
        admin_client,
        settings.supabase_bucket,
        object_key,
        SIGNED_URL_TTL_SECONDS,
    )

    return SummaryResponse(
        summary_id=summary["id"],
        markdown=summary["summary_markdown"],
        pdf_url=pdf_url,
    )


async def create_summary_pdf(
    summary_id: UUID,
    auth: AuthContext,
    settings: Settings,
) -> SummaryPdfResponse:
    user_client = await create_supabase_user_client(settings, auth.access_token)
    summary = await fetch_summary(user_client, str(summary_id))

    admin_client = await create_supabase_admin_client(settings)
    existing_object_key = summary.get("pdf_object_key")
    if isinstance(existing_object_key, str) and existing_object_key:
        pdf_url = await create_pdf_signed_url(
            admin_client,
            settings.supabase_bucket,
            existing_object_key,
            SIGNED_URL_TTL_SECONDS,
        )
        if not pdf_url:
            raise ExternalServiceError("Signed PDF URL was not returned.")
        return SummaryPdfResponse(summary_id=summary["id"], pdf_url=pdf_url)

    markdown = summary.get("summary_markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        raise ExternalServiceError("Summary markdown is missing; cannot generate PDF.")

    user_id = summary.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        raise ExternalServiceError("Summary user id is missing; cannot generate PDF.")

    pdf_bytes = await asyncio.to_thread(markdown_to_pdf_bytes, markdown)
    transcript = await fetch_transcript_by_id(admin_client, summary["transcript_id"])
    video_id = transcript.get("video_id")
    if not isinstance(video_id, str) or not video_id:
        video_id = "unknown-video"

    object_key = f"{user_id}/{video_id}/{summary_id}.pdf"
    await upload_pdf(
        admin_client,
        bucket=settings.supabase_bucket,
        object_key=object_key,
        pdf_bytes=pdf_bytes,
    )
    await update_summary_pdf_key(admin_client, summary_id=str(summary_id), pdf_object_key=object_key)

    pdf_url = await create_pdf_signed_url(
        admin_client,
        settings.supabase_bucket,
        object_key,
        SIGNED_URL_TTL_SECONDS,
    )
    if not pdf_url:
        raise ExternalServiceError("Signed PDF URL was not returned.")

    return SummaryPdfResponse(summary_id=summary["id"], pdf_url=pdf_url)

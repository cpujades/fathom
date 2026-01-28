from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fathom.api.deps.auth import AuthContext
from fathom.application.guards import validate_video_duration, validate_youtube_url
from fathom.core.config import Settings
from fathom.core.constants import SIGNED_URL_TTL_SECONDS
from fathom.core.errors import ExternalServiceError
from fathom.core.logging import log_context
from fathom.crud.supabase.jobs import create_job
from fathom.crud.supabase.storage_objects import create_pdf_signed_url, upload_pdf
from fathom.crud.supabase.summaries import fetch_summary, update_summary_pdf_key
from fathom.crud.supabase.transcripts import fetch_transcript_by_id
from fathom.schemas.summaries import SummarizeRequest, SummarizeResponse, SummaryPdfResponse, SummaryResponse
from fathom.services.downloader import fetch_video_metadata
from fathom.services.pdf import markdown_to_pdf_bytes
from fathom.services.supabase import create_supabase_admin_client, create_supabase_user_client

logger = logging.getLogger(__name__)


async def create_summary_job(
    request: SummarizeRequest,
    auth: AuthContext,
    settings: Settings,
) -> SummarizeResponse:
    url = str(request.url)
    with log_context(user_id=auth.user_id):
        logger.info("summarize request start")
        validate_youtube_url(url)
        metadata = await asyncio.to_thread(fetch_video_metadata, url)
        validate_video_duration(metadata.duration_seconds)
        logger.info(
            "video metadata validated",
            extra={
                "video_id": metadata.video_id,
                "duration_seconds": metadata.duration_seconds,
            },
        )

        client = await create_supabase_user_client(settings, auth.access_token)
        job = await create_job(client, url=url, user_id=auth.user_id)
        job_id = job["id"]
        logger.info("summarize job created", extra={"job_id": job_id})

    return SummarizeResponse(job_id=job_id)


async def get_summary_with_pdf(
    summary_id: UUID,
    auth: AuthContext,
    settings: Settings,
) -> SummaryResponse:
    summary_id_str = str(summary_id)
    with log_context(user_id=auth.user_id, summary_id=summary_id_str):
        user_client = await create_supabase_user_client(settings, auth.access_token)
        summary = await fetch_summary(user_client, summary_id_str)
        object_key = summary.get("pdf_object_key")
        has_pdf = isinstance(object_key, str) and bool(object_key)
        logger.info("summary fetched", extra={"has_pdf": has_pdf})
        if not has_pdf:
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
        logger.info("summary pdf signed url issued")

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
    summary_id_str = str(summary_id)
    with log_context(user_id=auth.user_id, summary_id=summary_id_str):
        user_client = await create_supabase_user_client(settings, auth.access_token)
        summary = await fetch_summary(user_client, summary_id_str)

        admin_client = await create_supabase_admin_client(settings)
        existing_object_key = summary.get("pdf_object_key")
        if isinstance(existing_object_key, str) and existing_object_key:
            logger.info("summary pdf already exists")
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

        logger.info("generating summary pdf")
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
        await update_summary_pdf_key(admin_client, summary_id=summary_id_str, pdf_object_key=object_key)
        logger.info("summary pdf uploaded", extra={"object_key": object_key})

        pdf_url = await create_pdf_signed_url(
            admin_client,
            settings.supabase_bucket,
            object_key,
            SIGNED_URL_TTL_SECONDS,
        )
        if not pdf_url:
            raise ExternalServiceError("Signed PDF URL was not returned.")

        logger.info("summary pdf signed url issued")
        return SummaryPdfResponse(summary_id=summary["id"], pdf_url=pdf_url)

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fathom.api.deps.auth import AuthContext
from fathom.core.config import Settings
from fathom.core.constants import SIGNED_URL_TTL_SECONDS, SUPABASE_PDF_BUCKET
from fathom.core.errors import ExternalServiceError
from fathom.core.logging import log_context
from fathom.crud.supabase.storage_objects import create_pdf_signed_url, upload_pdf
from fathom.crud.supabase.summaries import fetch_summary, update_summary_pdf_key
from fathom.crud.supabase.transcripts import fetch_transcript_by_id
from fathom.schemas.briefings import BriefingPdfResponse, BriefingResponse
from fathom.services.pdf import markdown_to_pdf_bytes
from fathom.services.supabase import create_supabase_admin_client, create_supabase_user_client

logger = logging.getLogger(__name__)


async def get_briefing(briefing_id: UUID, auth: AuthContext, settings: Settings) -> BriefingResponse:
    briefing_id_str = str(briefing_id)
    with log_context(user_id=auth.user_id, briefing_id=briefing_id_str):
        user_client = await create_supabase_user_client(settings, auth.access_token)
        summary = await fetch_summary(user_client, briefing_id_str)
        object_key = summary.get("pdf_object_key")
        has_pdf = isinstance(object_key, str) and bool(object_key)
        logger.info("briefing fetched", extra={"has_pdf": has_pdf})
        if not has_pdf:
            return BriefingResponse(
                briefing_id=summary["id"],
                markdown=summary["summary_markdown"],
                pdf_url=None,
            )

        admin_client = await create_supabase_admin_client(settings)
        pdf_url = await create_pdf_signed_url(
            admin_client,
            SUPABASE_PDF_BUCKET,
            object_key,
            SIGNED_URL_TTL_SECONDS,
        )
        logger.info("briefing pdf signed url issued")
        return BriefingResponse(
            briefing_id=summary["id"],
            markdown=summary["summary_markdown"],
            pdf_url=pdf_url,
        )


async def create_briefing_pdf(briefing_id: UUID, auth: AuthContext, settings: Settings) -> BriefingPdfResponse:
    briefing_id_str = str(briefing_id)
    with log_context(user_id=auth.user_id, briefing_id=briefing_id_str):
        user_client = await create_supabase_user_client(settings, auth.access_token)
        summary = await fetch_summary(user_client, briefing_id_str)

        admin_client = await create_supabase_admin_client(settings)
        existing_object_key = summary.get("pdf_object_key")
        if isinstance(existing_object_key, str) and existing_object_key:
            logger.info("briefing pdf already exists")
            pdf_url = await create_pdf_signed_url(
                admin_client,
                SUPABASE_PDF_BUCKET,
                existing_object_key,
                SIGNED_URL_TTL_SECONDS,
            )
            if not pdf_url:
                raise ExternalServiceError("Signed PDF URL was not returned.")
            return BriefingPdfResponse(briefing_id=summary["id"], pdf_url=pdf_url)

        markdown = summary.get("summary_markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            raise ExternalServiceError("Briefing markdown is missing; cannot generate PDF.")

        user_id = summary.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise ExternalServiceError("Briefing user id is missing; cannot generate PDF.")

        logger.info("generating briefing pdf")
        pdf_bytes = await asyncio.to_thread(markdown_to_pdf_bytes, markdown)
        transcript = await fetch_transcript_by_id(admin_client, summary["transcript_id"])
        video_id = transcript.get("video_id")
        if not isinstance(video_id, str) or not video_id:
            video_id = "unknown-video"

        object_key = f"{user_id}/{video_id}/{briefing_id}.pdf"
        await upload_pdf(
            admin_client,
            bucket=SUPABASE_PDF_BUCKET,
            object_key=object_key,
            pdf_bytes=pdf_bytes,
        )
        await update_summary_pdf_key(admin_client, summary_id=briefing_id_str, pdf_object_key=object_key)
        logger.info("briefing pdf uploaded", extra={"object_key": object_key})

        pdf_url = await create_pdf_signed_url(
            admin_client,
            SUPABASE_PDF_BUCKET,
            object_key,
            SIGNED_URL_TTL_SECONDS,
        )
        if not pdf_url:
            raise ExternalServiceError("Signed PDF URL was not returned.")

        logger.info("briefing pdf signed url issued")
        return BriefingPdfResponse(briefing_id=summary["id"], pdf_url=pdf_url)

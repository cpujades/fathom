from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from fathom.api.deps.auth import AuthContext
from fathom.application.briefings.contract import build_source_thumbnail_url, normalize_source, resolve_source_title
from fathom.core.config import Settings
from fathom.core.constants import SIGNED_URL_TTL_SECONDS, SUPABASE_PDF_BUCKET
from fathom.core.errors import ExternalServiceError
from fathom.core.logging import log_context
from fathom.crud.supabase.jobs import fetch_briefing_jobs_page
from fathom.crud.supabase.storage_objects import create_pdf_signed_url, upload_pdf
from fathom.crud.supabase.summaries import fetch_summaries_by_ids, fetch_summary, update_summary_pdf_key
from fathom.crud.supabase.transcripts import fetch_transcript_by_id, fetch_transcripts_by_ids
from fathom.schemas.briefings import (
    BriefingListItem,
    BriefingListResponse,
    BriefingListSort,
    BriefingPdfResponse,
    BriefingResponse,
    BriefingSourceFilter,
)
from fathom.services.pdf import markdown_to_pdf_bytes
from fathom.services.supabase import create_supabase_admin_client, create_supabase_user_client

logger = logging.getLogger(__name__)

DEFAULT_BRIEFINGS_PAGE_SIZE = 24
BRIEFINGS_SCAN_BATCH_SIZE = 200


async def get_briefing(briefing_id: UUID, auth: AuthContext, settings: Settings) -> BriefingResponse:
    briefing_id_str = str(briefing_id)
    with log_context(user_id=auth.user_id, briefing_id=briefing_id_str):
        user_client = await create_supabase_user_client(settings, auth.access_token)
        summary = await fetch_summary(user_client, briefing_id_str)
        object_key = summary.get("pdf_object_key")
        has_pdf = isinstance(object_key, str) and bool(object_key)
        logger.info("briefing.fetched", extra={"has_pdf": has_pdf})
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
        logger.info("briefing_pdf.signed_url.issued")
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
            logger.info("briefing_pdf.cache_hit")
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

        logger.info("briefing_pdf.generation.started")
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
        logger.info("briefing_pdf.uploaded", extra={"object_key": object_key})

        pdf_url = await create_pdf_signed_url(
            admin_client,
            SUPABASE_PDF_BUCKET,
            object_key,
            SIGNED_URL_TTL_SECONDS,
        )
        if not pdf_url:
            raise ExternalServiceError("Signed PDF URL was not returned.")

        logger.info("briefing_pdf.signed_url.issued")
        return BriefingPdfResponse(briefing_id=summary["id"], pdf_url=pdf_url)


async def list_briefings_for_user(
    *,
    user_id: str,
    settings: Settings,
    limit: int = DEFAULT_BRIEFINGS_PAGE_SIZE,
    offset: int = 0,
    query: str | None = None,
    sort: BriefingListSort = "newest",
    source_type: BriefingSourceFilter = "all",
) -> BriefingListResponse:
    admin_client = await create_supabase_admin_client(settings)
    normalized_query = _normalize_query(query)
    sort_desc = sort == "newest"

    if normalized_query is None and source_type == "all":
        jobs, total_count = await fetch_briefing_jobs_page(
            admin_client,
            user_id=user_id,
            limit=limit,
            offset=offset,
            sort_desc=sort_desc,
        )
        items = await _build_briefing_list_items(admin_client, jobs)
        return BriefingListResponse(
            items=items,
            total_count=total_count,
            limit=limit,
            offset=offset,
            has_more=offset + len(items) < total_count,
            query=None,
            sort=sort,
            source_type=source_type,
        )

    matched_items: list[BriefingListItem] = []
    matched_count = 0
    scan_offset = 0

    while True:
        batch, _ = await fetch_briefing_jobs_page(
            admin_client,
            user_id=user_id,
            limit=BRIEFINGS_SCAN_BATCH_SIZE,
            offset=scan_offset,
            sort_desc=sort_desc,
        )
        if not batch:
            break

        hydrated_items = await _build_briefing_list_items(admin_client, batch)
        for item in hydrated_items:
            if source_type != "all" and item.source_type != source_type:
                continue
            if normalized_query and not _briefing_matches_query(item, normalized_query):
                continue
            if matched_count >= offset and len(matched_items) < limit:
                matched_items.append(item)
            matched_count += 1

        scan_offset += len(batch)
        if len(batch) < BRIEFINGS_SCAN_BATCH_SIZE:
            break

    return BriefingListResponse(
        items=matched_items,
        total_count=matched_count,
        limit=limit,
        offset=offset,
        has_more=offset + len(matched_items) < matched_count,
        query=normalized_query,
        sort=sort,
        source_type=source_type,
    )


async def _build_briefing_list_items(admin_client: Any, jobs: Sequence[dict[str, Any]]) -> list[BriefingListItem]:
    summary_ids = [str(job.get("summary_id")) for job in jobs if job.get("summary_id")]
    summaries = await fetch_summaries_by_ids(admin_client, summary_ids)
    transcript_ids = [str(summary.get("transcript_id")) for summary in summaries if summary.get("transcript_id")]
    transcripts = await fetch_transcripts_by_ids(admin_client, transcript_ids)

    summary_by_id = {str(summary.get("id")): summary for summary in summaries if summary.get("id")}
    transcript_by_id = {str(transcript.get("id")): transcript for transcript in transcripts if transcript.get("id")}

    items: list[BriefingListItem] = []
    for job in jobs:
        job_id = job.get("id")
        summary_id = job.get("summary_id")
        created_at = job.get("created_at")
        url = str(job.get("url") or "").strip()
        if not job_id or not summary_id or not created_at or not url:
            continue

        normalized_source = normalize_source(url)
        summary = summary_by_id.get(str(summary_id))
        transcript_id = summary.get("transcript_id") if isinstance(summary, dict) else None
        transcript = transcript_by_id.get(str(transcript_id)) if transcript_id else None

        source_title = transcript.get("source_title") if isinstance(transcript, dict) else None
        source_author = transcript.get("source_author") if isinstance(transcript, dict) else None
        source_duration_seconds = transcript.get("source_length_seconds") if isinstance(transcript, dict) else None
        source_thumbnail_url = build_source_thumbnail_url(
            normalized_source,
            transcript.get("video_id") if isinstance(transcript, dict) else None,
        )

        items.append(
            BriefingListItem(
                session_id=job_id,
                briefing_id=summary_id,
                title=resolve_source_title(normalized_source, source_title),
                author=_clean_optional_text(source_author),
                source_url=normalized_source.canonical_url,
                source_host=_resolve_source_host(normalized_source.canonical_url),
                source_type=normalized_source.source_type,
                created_at=created_at,
                source_duration_seconds=(
                    _coerce_positive_int(source_duration_seconds) or _coerce_positive_int(job.get("duration_seconds"))
                ),
                source_thumbnail_url=source_thumbnail_url,
                session_path=f"/app/briefings/sessions/{job_id}",
            )
        )

    return items


def _normalize_query(value: str | None) -> str | None:
    if not value:
        return None
    normalized = " ".join(value.split()).strip()
    return normalized or None


def _clean_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _resolve_source_host(source_url: str) -> str:
    host = urlparse(source_url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "source"


def _coerce_positive_int(value: Any) -> int | None:
    if not isinstance(value, int) or value <= 0:
        return None
    return value


def _briefing_matches_query(item: BriefingListItem, query: str) -> bool:
    haystack = " ".join(
        filter(
            None,
            [
                item.title,
                item.author or "",
                item.source_url,
                item.source_host,
            ],
        )
    ).lower()
    return all(token in haystack for token in query.lower().split())

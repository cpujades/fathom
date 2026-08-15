from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fathom.application.briefings.contract import NormalizedSource, normalize_source
from fathom.application.briefings.sessions.queries import build_session_snapshot, job_has_ready_summary
from fathom.application.guards import validate_video_duration, validate_youtube_url
from fathom.application.identity import AuthenticatedUser
from fathom.application.publications import find_listed_publication_for_source
from fathom.application.usage import ensure_usage_allowed, record_usage_for_job
from fathom.core.config import Settings
from fathom.core.constants import GROQ_TRANSCRIPT_PROVIDER_MODEL, SUMMARY_PROMPT_KEY_EVIDENCE
from fathom.core.errors import NotFoundError, PublicBriefingAvailableError, UsageSettlementError
from fathom.core.logging import log_context
from fathom.crud.supabase.job_events import record_job_event_best_effort
from fathom.crud.supabase.jobs import (
    JobCreateResolution,
    JobLeaseLostError,
    archive_job,
    create_or_reuse_job,
    fetch_active_job_for_source,
    fetch_job,
    fetch_reusable_job_for_source,
    mark_job_finalization_retry,
    mark_job_succeeded,
    restore_job,
)
from fathom.crud.supabase.summaries import fetch_summary_by_keys
from fathom.crud.supabase.transcripts import (
    fetch_transcript_by_hash,
    fetch_transcript_by_video_id,
    fetch_transcript_segments,
)
from fathom.schemas.briefing_sessions import (
    BriefingSessionCreateRequest,
    BriefingSessionResolution,
    BriefingSessionResponse,
)
from fathom.services.downloader import SOURCE_METADATA_TIMEOUT_SECONDS, fetch_video_metadata_with_deadline
from fathom.services.summarizer import OPENROUTER_MODEL
from fathom.services.supabase import (
    create_supabase_admin_client,
    create_supabase_user_client,
    managed_supabase_client,
)

logger = logging.getLogger(__name__)


async def create_briefing_session(
    request: BriefingSessionCreateRequest,
    auth: AuthenticatedUser,
    settings: Settings,
) -> BriefingSessionResponse:
    async with (
        managed_supabase_client(await create_supabase_user_client(settings, auth.access_token)) as user_client,
        managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client,
    ):
        return await _create_briefing_session(request, auth, settings, user_client, admin_client)


async def _create_briefing_session(
    request: BriefingSessionCreateRequest,
    auth: AuthenticatedUser,
    settings: Settings,
    user_client: Any,
    admin_client: Any,
) -> BriefingSessionResponse:
    submitted_url = str(request.url)
    with log_context(user_id=auth.user_id):
        logger.info("briefing_session.create.started")
        validate_youtube_url(submitted_url)
        source = normalize_source(submitted_url)

        active_job = await fetch_active_job_for_source(
            user_client,
            user_id=auth.user_id,
            source_key=source.source_identity_key,
        )
        if active_job:
            logger.info("briefing_session.reused_active", extra={"session_id": active_job["id"]})
            return await build_session_snapshot(
                user_client=user_client,
                admin_client=admin_client,
                job=active_job,
                source=source,
                resolution_type="joined_existing",
            )

        completed_job = await fetch_reusable_job_for_source(
            user_client,
            user_id=auth.user_id,
            source_key=source.source_identity_key,
        )
        if completed_job and not await job_has_ready_summary(admin_client, completed_job):
            logger.warning(
                "briefing_session.reusable_summary_not_ready",
                extra={"session_id": completed_job["id"]},
            )
            completed_job = None
        if completed_job:
            if str(completed_job.get("status") or "") == "deleted":
                await restore_job(admin_client, job_id=str(completed_job["id"]))
                restored_job = await fetch_job(user_client, str(completed_job["id"]))
                logger.info("briefing_session.restored_archived", extra={"session_id": restored_job["id"]})
                return await build_session_snapshot(
                    user_client=user_client,
                    admin_client=admin_client,
                    job=restored_job,
                    source=source,
                    resolution_type="reused_ready",
                )
            logger.info("briefing_session.reused_ready", extra={"session_id": completed_job["id"]})
            return await build_session_snapshot(
                user_client=user_client,
                admin_client=admin_client,
                job=completed_job,
                source=source,
                resolution_type="reused_ready",
            )

        if await find_listed_publication_for_source(
            admin_client,
            source_key=source.source_identity_key,
        ):
            raise PublicBriefingAvailableError("This source already has a free briefing in Explore.")

        metadata = await fetch_video_metadata_with_deadline(
            source.canonical_url,
            deadline_seconds=SOURCE_METADATA_TIMEOUT_SECONDS,
        )
        validate_video_duration(metadata.duration_seconds)
        logger.info(
            "briefing_session.source.validated",
            extra={"video_id": metadata.video_id, "duration_seconds": metadata.duration_seconds},
        )

        await ensure_usage_allowed(
            user_id=auth.user_id,
            duration_seconds=metadata.duration_seconds,
            settings=settings,
        )

        cached_summary = await find_ready_cached_summary(admin_client, source)
        if cached_summary:
            cached_resolution = await create_ready_reused_session(
                user_id=auth.user_id,
                source=source,
                duration_seconds=metadata.duration_seconds,
                summary_id=str(cached_summary["id"]),
                user_client=user_client,
                admin_client=admin_client,
                settings=settings,
            )
            ready_job = cached_resolution.job
            response_resolution: BriefingSessionResolution = cached_resolution.resolution_type
            if cached_resolution.resolution_type == "new":
                response_resolution = "reused_ready"
                await record_job_event_best_effort(
                    admin_client,
                    logger,
                    job_id=str(ready_job["id"]),
                    event_type="session_created",
                    stage="cached",
                    message="Ready session created from cached summary.",
                    metadata={
                        "resolution_type": response_resolution,
                        "video_id": metadata.video_id,
                        "duration_seconds": metadata.duration_seconds,
                        "summary_id": str(cached_summary["id"]),
                    },
                )
            logger.info(
                "briefing_session.reused_cached",
                extra={
                    "session_id": ready_job["id"],
                    "resolution_type": response_resolution,
                },
            )
            return await build_session_snapshot(
                user_client=user_client,
                admin_client=admin_client,
                job=ready_job,
                source=source,
                resolution_type=response_resolution,
            )

        job_resolution = await create_or_reuse_job(
            admin_client,
            url=source.canonical_url,
            source_key=source.source_identity_key,
            user_id=auth.user_id,
            duration_seconds=metadata.duration_seconds,
        )
        job = await fetch_job(user_client, str(job_resolution.job["id"]))
        logger.info(
            "briefing_session.resolved",
            extra={
                "session_id": job["id"],
                "resolution_type": job_resolution.resolution_type,
            },
        )
        if job_resolution.resolution_type == "new":
            await record_job_event_best_effort(
                admin_client,
                logger,
                job_id=str(job["id"]),
                event_type="session_created",
                stage="queued",
                message="Briefing session created.",
                metadata={
                    "resolution_type": "new",
                    "video_id": metadata.video_id,
                    "duration_seconds": metadata.duration_seconds,
                },
            )
        return await build_session_snapshot(
            user_client=user_client,
            admin_client=admin_client,
            job=job,
            source=source,
            resolution_type=job_resolution.resolution_type,
        )


async def create_ready_reused_session(
    *,
    user_id: str,
    source: NormalizedSource,
    duration_seconds: int | None,
    summary_id: str,
    user_client: Any,
    admin_client: Any,
    settings: Settings,
) -> JobCreateResolution:
    job_resolution = await create_or_reuse_job(
        admin_client,
        url=source.canonical_url,
        source_key=source.source_identity_key,
        user_id=user_id,
        duration_seconds=duration_seconds,
        summary_id=summary_id,
    )
    if job_resolution.resolution_type != "new":
        job = await fetch_job(user_client, str(job_resolution.job["id"]))
        return JobCreateResolution(job=job, resolution_type=job_resolution.resolution_type)

    session_id = str(job_resolution.job["id"])
    lease_token = str(job_resolution.job.get("lease_token") or "")
    if not lease_token:
        raise UsageSettlementError("Cached briefing finalization did not receive a job lease.")
    try:
        await record_usage_for_job(
            user_id=user_id,
            job_id=session_id,
            lease_token=lease_token,
            duration_seconds=duration_seconds,
            settings=settings,
            admin_client=admin_client,
        )
        await mark_job_succeeded(
            admin_client,
            job_id=session_id,
            summary_id=summary_id,
            lease_token=lease_token,
        )
    except UsageSettlementError as exc:
        logger.warning(
            "briefing_session.usage_settlement.retrying",
            extra={"session_id": session_id},
            exc_info=True,
        )
        try:
            await mark_job_finalization_retry(
                admin_client,
                job_id=session_id,
                lease_token=lease_token,
                error_code=exc.code,
                error_message=exc.detail,
                run_after=billing_retry_time(),
            )
        except JobLeaseLostError:
            logger.warning(
                "briefing_session.usage_settlement.retry_lease_lost",
                extra={"session_id": session_id},
            )
    except JobLeaseLostError:
        logger.warning(
            "briefing_session.finalization_lease_lost",
            extra={"session_id": session_id},
        )
    job = await fetch_job(user_client, session_id)
    return JobCreateResolution(job=job, resolution_type="new")


async def find_ready_cached_summary(admin_client: Any, source: NormalizedSource) -> dict[str, Any] | None:
    transcript = None
    if source.video_id:
        transcript = await fetch_transcript_by_video_id(
            admin_client,
            video_id=source.video_id,
            provider_model=GROQ_TRANSCRIPT_PROVIDER_MODEL,
        )

    if not transcript:
        transcript = await fetch_transcript_by_hash(
            admin_client,
            url_hash=hash_url(source.canonical_url),
            provider_model=GROQ_TRANSCRIPT_PROVIDER_MODEL,
        )

    if not transcript:
        return None

    transcript_id = str(transcript["id"])
    segments = await fetch_transcript_segments(admin_client, transcript_id=transcript_id)
    if not segments:
        return None
    summary = await fetch_summary_by_keys(
        admin_client,
        transcript_id=transcript_id,
        prompt_key=SUMMARY_PROMPT_KEY_EVIDENCE,
        summary_model=OPENROUTER_MODEL,
    )
    if not summary:
        return None

    markdown = summary.get("summary_markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        return None
    return summary


async def delete_briefing_session(
    session_id: UUID,
    auth: AuthenticatedUser,
    settings: Settings,
) -> None:
    session_id_str = str(session_id)
    with log_context(user_id=auth.user_id, session_id=session_id_str):
        async with managed_supabase_client(
            await create_supabase_user_client(settings, auth.access_token)
        ) as user_client:
            job = await fetch_job(user_client, session_id_str)
            if str(job.get("status") or "") == "deleted":
                return
            if not job.get("summary_id"):
                raise NotFoundError("Briefing session not found.")
        async with managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client:
            await archive_job(admin_client, job_id=session_id_str)


def hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def billing_retry_time() -> datetime:
    return datetime.now(UTC) + timedelta(seconds=5)

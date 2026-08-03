from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fathom.application.briefings.access import fetch_summary_for_owned_job
from fathom.application.briefings.contract import (
    NormalizedSource,
    build_briefing_session_snapshot,
    normalize_source,
)
from fathom.application.identity import AuthenticatedUser
from fathom.core.config import Settings
from fathom.core.errors import NotFoundError
from fathom.core.logging import log_context
from fathom.crud.supabase.jobs import fetch_job
from fathom.crud.supabase.transcripts import fetch_transcript_by_id
from fathom.schemas.briefing_sessions import BriefingSessionResolution, BriefingSessionResponse
from fathom.services.supabase import (
    create_supabase_admin_client,
    create_supabase_user_client,
    managed_supabase_client,
)

logger = logging.getLogger(__name__)


async def get_briefing_session(
    session_id: UUID,
    auth: AuthenticatedUser,
    settings: Settings,
) -> BriefingSessionResponse:
    session_id_str = str(session_id)
    with log_context(user_id=auth.user_id, session_id=session_id_str):
        async with (
            managed_supabase_client(await create_supabase_user_client(settings, auth.access_token)) as user_client,
            managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client,
        ):
            job = await fetch_job(user_client, session_id_str)
            if str(job.get("status") or "") == "deleted":
                raise NotFoundError("Briefing session not found.")
            source = normalize_source(job["url"])
            logger.info(
                "briefing_session.fetched",
                extra={"state": job.get("stage"), "status": job.get("status")},
            )
            return await build_session_snapshot(
                user_client=user_client,
                admin_client=admin_client,
                job=job,
                source=source,
            )


async def build_session_snapshot(
    *,
    user_client: Any,
    admin_client: Any,
    job: dict[str, Any],
    source: NormalizedSource,
    resolution_type: BriefingSessionResolution | None = None,
) -> BriefingSessionResponse:
    summary, transcript = await fetch_summary_and_transcript_for_job(admin_client, job)
    return build_briefing_session_snapshot(
        job=job,
        source=source,
        resolution_type=resolution_type,
        summary=summary,
        transcript=transcript,
    )


async def fetch_summary_and_transcript_for_job(
    admin_client: Any,
    job: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    summary = await fetch_summary_for_owned_job(admin_client=admin_client, job=job)
    if summary is None:
        return None, None

    transcript_id = summary.get("transcript_id")
    if not transcript_id:
        return summary, None

    transcript = await fetch_transcript_by_id(admin_client, str(transcript_id))
    return summary, transcript


async def job_has_ready_summary(admin_client: Any, job: dict[str, Any]) -> bool:
    summary = await fetch_summary_for_owned_job(admin_client=admin_client, job=job)
    if summary is None:
        return False

    markdown = summary.get("summary_markdown")
    return summary.get("status") == "ready" and isinstance(markdown, str) and bool(markdown.strip())

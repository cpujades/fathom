from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from fathom.application.briefings.contract import build_source_thumbnail_url, normalize_source, resolve_source_title
from fathom.application.identity import AuthenticatedUser
from fathom.core.config import Settings
from fathom.core.constants import GROQ_TRANSCRIPT_PROVIDER_MODEL, SUMMARY_PROMPT_KEY_EVIDENCE
from fathom.core.errors import ForbiddenError, InvalidRequestError, NotFoundError
from fathom.crud.supabase.jobs import (
    fetch_active_job_for_source,
    fetch_job,
    fetch_jobs_by_ids,
    fetch_reusable_job_for_source,
)
from fathom.crud.supabase.publications import (
    create_publication,
    fetch_library_jobs_for_sources,
    fetch_listed_publication_for_source,
    fetch_listed_publications_page,
    fetch_owner_publication,
    fetch_public_publication,
    fetch_public_publications_by_slugs,
    fetch_publication_job,
    save_publication,
    update_publication,
)
from fathom.crud.supabase.summaries import fetch_summaries_by_ids, fetch_summary
from fathom.crud.supabase.transcripts import fetch_transcript_by_id, fetch_transcripts_by_ids
from fathom.schemas.publications import (
    ExploreBriefingItem,
    ExploreBriefingResponse,
    ExploreTopic,
    PublicationLibraryEntriesResponse,
    PublicationLibraryEntryResponse,
    PublicationSourceMatchResponse,
    PublicationStateResponse,
    PublicationUpdateRequest,
    PublicBriefingResponse,
)
from fathom.services.summarizer import OPENROUTER_MODEL
from fathom.services.supabase import (
    create_supabase_admin_client,
    create_supabase_user_client,
    managed_supabase_client,
)


async def get_owner_publication(
    session_id: UUID,
    auth: AuthenticatedUser,
    settings: Settings,
) -> PublicationStateResponse:
    async with (
        managed_supabase_client(await create_supabase_user_client(settings, auth.access_token)) as user_client,
        managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client,
    ):
        await fetch_job(user_client, str(session_id))
        publication = await fetch_owner_publication(admin_client, owner_job_id=str(session_id))
    return _publication_state(publication, can_list=_can_list(auth.user_id, settings))


async def set_owner_publication(
    session_id: UUID,
    request: PublicationUpdateRequest,
    auth: AuthenticatedUser,
    settings: Settings,
) -> PublicationStateResponse:
    session_id_str = str(session_id)
    async with (
        managed_supabase_client(await create_supabase_user_client(settings, auth.access_token)) as user_client,
        managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client,
    ):
        job = await fetch_job(user_client, session_id_str)
        publication = await fetch_owner_publication(admin_client, owner_job_id=session_id_str)
        if publication and publication.get("moderation_status") == "blocked":
            raise ForbiddenError("This public briefing has been blocked.")

        can_list = _can_list(auth.user_id, settings)
        visibility = request.visibility
        if visibility == "listed" and not can_list:
            raise ForbiddenError("Only Talven can add briefings to Explore.")
        if visibility != "private" and str(job.get("status") or "") != "succeeded":
            raise InvalidRequestError("Only a completed briefing can be published.")

        topic = _normalize_topic(request.topic) if visibility == "listed" else None
        if visibility == "listed" and topic is None:
            raise InvalidRequestError("Choose a topic before adding this briefing to Explore.")

        if publication is None:
            if visibility == "private":
                return _publication_state(None, can_list=can_list)
            summary_id = job.get("summary_id")
            if not summary_id:
                raise InvalidRequestError("Only a completed briefing can be published.")
            publication = await create_publication(
                admin_client,
                owner_user_id=auth.user_id,
                owner_job_id=session_id_str,
                summary_id=str(summary_id),
                visibility=visibility,
                topic=topic,
            )
        else:
            publication = await update_publication(
                admin_client,
                publication=publication,
                visibility=visibility,
                topic=topic,
            )

    return _publication_state(publication, can_list=can_list)


async def get_public_briefing(public_slug: str, settings: Settings) -> PublicBriefingResponse:
    async with managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client:
        publication = await _require_publication(admin_client, public_slug)
        return await _build_public_briefing(admin_client, publication)


async def list_explore_briefings(
    *,
    settings: Settings,
    limit: int,
    offset: int,
    topic: ExploreTopic | None,
) -> ExploreBriefingResponse:
    async with managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client:
        publications, total_count = await fetch_listed_publications_page(
            admin_client,
            limit=limit,
            offset=offset,
            topic=topic.value if topic else None,
        )
        items = await _build_explore_items(admin_client, publications)
    return ExploreBriefingResponse(
        items=items,
        total_count=total_count,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total_count,
        topic=topic,
        available_topics=list(ExploreTopic),
    )


async def get_publication_library_entries(
    public_slugs: list[str],
    auth: AuthenticatedUser,
    settings: Settings,
) -> PublicationLibraryEntriesResponse:
    async with (
        managed_supabase_client(await create_supabase_user_client(settings, auth.access_token)) as user_client,
        managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client,
    ):
        publications = await fetch_public_publications_by_slugs(admin_client, public_slugs=public_slugs)
        source_keys = list(dict.fromkeys(str(publication["source_key"]) for publication in publications))
        jobs = await fetch_library_jobs_for_sources(
            user_client,
            user_id=auth.user_id,
            source_keys=source_keys,
        )

    entries_by_source = _library_entries_by_source(jobs)
    return PublicationLibraryEntriesResponse(
        entries={
            str(publication["public_slug"]): entries_by_source.get(
                str(publication["source_key"]),
                PublicationLibraryEntryResponse(state="not_saved"),
            )
            for publication in publications
        }
    )


async def match_listed_publication(
    source_url: str,
    auth: AuthenticatedUser,
    settings: Settings,
) -> PublicationSourceMatchResponse:
    source = normalize_source(source_url)
    async with (
        managed_supabase_client(await create_supabase_user_client(settings, auth.access_token)) as user_client,
        managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client,
    ):
        match = await find_listed_publication_for_source(
            admin_client,
            source_key=source.source_identity_key,
        )
        library_entry = (
            await _find_library_entry(
                user_client,
                user_id=auth.user_id,
                source_key=source.source_identity_key,
            )
            if match
            else None
        )
    return PublicationSourceMatchResponse(match=match, library_entry=library_entry)


async def get_publication_library_entry(
    public_slug: str,
    auth: AuthenticatedUser,
    settings: Settings,
) -> PublicationLibraryEntryResponse:
    async with (
        managed_supabase_client(await create_supabase_user_client(settings, auth.access_token)) as user_client,
        managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client,
    ):
        publication = await _require_publication(admin_client, public_slug)
        owner_job = await fetch_publication_job(admin_client, job_id=str(publication["owner_job_id"]))
        return await _find_library_entry(
            user_client,
            user_id=auth.user_id,
            source_key=str(owner_job["source_key"]),
        )


async def save_public_briefing(
    public_slug: str,
    auth: AuthenticatedUser,
    settings: Settings,
) -> PublicationLibraryEntryResponse:
    async with managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client:
        await _require_publication(admin_client, public_slug)
        result = await save_publication(
            admin_client,
            user_id=auth.user_id,
            public_slug=public_slug,
        )
    return _library_entry_from_job(dict(result["job"]))


async def find_listed_publication_for_source(
    admin_client: Any,
    *,
    source_key: str,
) -> ExploreBriefingItem | None:
    """Return a Listed publication only when it matches the current generation contract."""
    publication = await fetch_listed_publication_for_source(admin_client, source_key=source_key)
    if publication is None:
        return None

    item, summary, transcript = await _hydrate_publication(admin_client, publication)
    if not _uses_current_generation_contract(summary, transcript):
        return None
    return _explore_item(publication, item)


async def _require_publication(admin_client: Any, public_slug: str) -> dict[str, Any]:
    publication = await fetch_public_publication(admin_client, public_slug=public_slug)
    if publication is None:
        raise NotFoundError("Public briefing not found.")
    return publication


async def _build_public_briefing(admin_client: Any, publication: dict[str, Any]) -> PublicBriefingResponse:
    item, summary, _ = await _hydrate_publication(admin_client, publication)
    published_at = publication.get("published_at")
    if published_at is None:
        raise NotFoundError("Public briefing not found.")
    return PublicBriefingResponse(
        **item,
        visibility=publication["visibility"],
        topic=publication.get("topic"),
        markdown=summary["summary_markdown"],
        published_at=published_at,
        listed_at=publication.get("listed_at"),
    )


def _explore_item(publication: dict[str, Any], item: dict[str, Any]) -> ExploreBriefingItem:
    topic = publication.get("topic")
    listed_at = publication.get("listed_at")
    if publication.get("visibility") != "listed" or not topic or listed_at is None:
        raise NotFoundError("Explore briefing not found.")
    return ExploreBriefingItem(
        **item,
        topic=topic,
        listed_at=listed_at,
    )


async def _hydrate_publication(
    admin_client: Any,
    publication: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    job, summary = await asyncio.gather(
        fetch_publication_job(admin_client, job_id=str(publication["owner_job_id"])),
        fetch_summary(admin_client, str(publication["summary_id"])),
    )
    transcript_id = summary.get("transcript_id")
    transcript = await fetch_transcript_by_id(admin_client, str(transcript_id)) if transcript_id else None
    return _build_publication_item(publication, job, summary, transcript), summary, transcript


async def _build_explore_items(
    admin_client: Any,
    publications: list[dict[str, Any]],
) -> list[ExploreBriefingItem]:
    if not publications:
        return []

    job_ids = list(dict.fromkeys(str(item["owner_job_id"]) for item in publications))
    summary_ids = list(dict.fromkeys(str(item["summary_id"]) for item in publications))
    jobs, summaries = await asyncio.gather(
        fetch_jobs_by_ids(admin_client, job_ids),
        fetch_summaries_by_ids(admin_client, summary_ids),
    )
    transcript_ids = list(
        dict.fromkeys(str(summary["transcript_id"]) for summary in summaries if summary.get("transcript_id"))
    )
    transcripts = await fetch_transcripts_by_ids(admin_client, transcript_ids)

    jobs_by_id = {str(job["id"]): job for job in jobs}
    summaries_by_id = {str(summary["id"]): summary for summary in summaries}
    transcripts_by_id = {str(transcript["id"]): transcript for transcript in transcripts}

    items: list[ExploreBriefingItem] = []
    for publication in publications:
        job = jobs_by_id.get(str(publication["owner_job_id"]))
        summary = summaries_by_id.get(str(publication["summary_id"]))
        if job is None or summary is None:
            raise NotFoundError("Explore briefing not found.")
        transcript_id = summary.get("transcript_id")
        transcript = transcripts_by_id.get(str(transcript_id)) if transcript_id else None
        item = _build_publication_item(publication, job, summary, transcript)
        items.append(_explore_item(publication, item))
    return items


def _build_publication_item(
    publication: dict[str, Any],
    job: dict[str, Any],
    summary: dict[str, Any],
    transcript: dict[str, Any] | None,
) -> dict[str, Any]:
    if job.get("status") != "succeeded" or str(job.get("summary_id")) != str(publication.get("summary_id")):
        raise NotFoundError("Public briefing not found.")

    if str(summary.get("id")) != str(publication.get("summary_id")) or summary.get("status") != "ready":
        raise NotFoundError("Public briefing not found.")
    markdown = summary.get("summary_markdown")
    if "summary_markdown" in summary and (not isinstance(markdown, str) or not markdown.strip()):
        raise NotFoundError("Public briefing not found.")
    if summary.get("transcript_id") and transcript is None:
        raise NotFoundError("Public briefing not found.")

    source = normalize_source(str(job["url"]))
    title = resolve_source_title(source, transcript.get("source_title") if transcript else None)
    author = _clean_optional_text(transcript.get("source_author") if transcript else None)
    duration = _positive_int(transcript.get("source_length_seconds") if transcript else None)
    duration = duration or _positive_int(job.get("duration_seconds"))
    public_slug = str(publication["public_slug"])
    item = {
        "public_slug": public_slug,
        "public_path": f"/b/{public_slug}",
        "title": title,
        "author": author,
        "source_url": source.canonical_url,
        "source_type": source.source_type,
        "source_duration_seconds": duration,
        "source_thumbnail_url": build_source_thumbnail_url(
            source,
            transcript.get("video_id") if transcript else None,
        ),
    }
    return item


async def _find_library_entry(
    user_client: Any,
    *,
    user_id: str,
    source_key: str,
) -> PublicationLibraryEntryResponse:
    active_job = await fetch_active_job_for_source(user_client, user_id=user_id, source_key=source_key)
    if active_job:
        return _library_entry_from_job(active_job)
    job = await fetch_reusable_job_for_source(user_client, user_id=user_id, source_key=source_key)
    if job and job.get("status") == "succeeded":
        return _library_entry_from_job(job)
    return PublicationLibraryEntryResponse(state="not_saved")


def _library_entry_from_job(job: dict[str, Any]) -> PublicationLibraryEntryResponse:
    job_id = job.get("id")
    status = str(job.get("status") or "")
    if not job_id:
        raise NotFoundError("Library entry not found.")
    state = "saved" if status == "succeeded" else "processing"
    return PublicationLibraryEntryResponse(
        state=state,
        session_id=job_id,
        session_path=f"/app/briefings/sessions/{job_id}",
    )


def _publication_state(publication: dict[str, Any] | None, *, can_list: bool) -> PublicationStateResponse:
    if publication is None:
        return PublicationStateResponse(
            visibility="private",
            can_list=can_list,
            available_topics=list(ExploreTopic),
        )
    public_slug = str(publication["public_slug"])
    return PublicationStateResponse(
        public_slug=public_slug,
        public_path=f"/b/{public_slug}",
        visibility=publication["visibility"],
        topic=publication.get("topic"),
        published_at=publication.get("published_at"),
        listed_at=publication.get("listed_at"),
        can_list=can_list,
        available_topics=list(ExploreTopic),
    )


def _uses_current_generation_contract(
    summary: dict[str, Any],
    transcript: dict[str, Any] | None,
) -> bool:
    return bool(
        transcript
        and transcript.get("provider_model") == GROQ_TRANSCRIPT_PROVIDER_MODEL
        and summary.get("prompt_key") == SUMMARY_PROMPT_KEY_EVIDENCE
        and summary.get("summary_model") == OPENROUTER_MODEL
    )


def _can_list(user_id: str, settings: Settings) -> bool:
    return user_id in settings.explore_operator_user_ids


def _normalize_topic(topic: str | None) -> str | None:
    if not topic:
        return None
    normalized = "-".join(topic.lower().split()).strip("-")
    return normalized or None


def _library_entries_by_source(jobs: list[dict[str, Any]]) -> dict[str, PublicationLibraryEntryResponse]:
    active: dict[str, PublicationLibraryEntryResponse] = {}
    reusable: dict[str, PublicationLibraryEntryResponse] = {}
    for job in jobs:
        source_key = str(job.get("source_key") or "")
        status = str(job.get("status") or "")
        if not source_key:
            continue
        if status in {"queued", "running"} and source_key not in active:
            active[source_key] = _library_entry_from_job(job)
        elif status in {"succeeded", "deleted"} and source_key not in reusable:
            reusable[source_key] = (
                _library_entry_from_job(job)
                if status == "succeeded"
                else PublicationLibraryEntryResponse(state="not_saved")
            )
    entries = dict(reusable)
    entries.update(active)
    return entries


def _clean_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _positive_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None

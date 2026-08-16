from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from fathom.schemas.briefing_sessions import BriefingSourceType

PublicationVisibility = Literal["private", "unlisted", "listed"]
PublicPublicationVisibility = Literal["unlisted", "listed"]
LibraryEntryState = Literal["not_saved", "processing", "saved"]


class ExploreTopic(StrEnum):
    BUSINESS = "business"
    CULTURE = "culture"
    FINANCE = "finance"
    HEALTH = "health"
    LIFE = "life"
    PRODUCTIVITY = "productivity"
    PSYCHOLOGY = "psychology"
    SCIENCE = "science"
    SELF_IMPROVEMENT = "self-improvement"
    SOCIETY = "society"
    TECHNOLOGY = "technology"


class PublicationUpdateRequest(BaseModel):
    visibility: PublicationVisibility
    topic: ExploreTopic | None = None


class PublicationStateResponse(BaseModel):
    public_slug: str | None = None
    public_path: str | None = None
    visibility: PublicationVisibility
    topic: ExploreTopic | None = None
    published_at: datetime | None = None
    listed_at: datetime | None = None
    can_list: bool
    available_topics: list[ExploreTopic]


class PublicBriefingResponse(BaseModel):
    public_slug: str
    public_path: str
    visibility: PublicPublicationVisibility
    topic: ExploreTopic | None = None
    title: str
    author: str | None = None
    source_url: str
    source_type: BriefingSourceType
    source_duration_seconds: int | None = None
    source_thumbnail_url: str | None = None
    markdown: str
    published_at: datetime
    listed_at: datetime | None = None


class ExploreBriefingItem(BaseModel):
    public_slug: str
    public_path: str
    topic: ExploreTopic
    title: str
    author: str | None = None
    source_url: str
    source_type: BriefingSourceType
    source_duration_seconds: int | None = None
    source_thumbnail_url: str | None = None
    listed_at: datetime


class ExploreBriefingResponse(BaseModel):
    items: list[ExploreBriefingItem]
    total_count: int
    limit: int
    offset: int
    has_more: bool
    topic: ExploreTopic | None = None
    available_topics: list[ExploreTopic]


class PublicationLibraryEntryResponse(BaseModel):
    state: LibraryEntryState
    session_id: UUID | None = None
    session_path: str | None = None


class PublicationLibraryEntriesRequest(BaseModel):
    public_slugs: list[str] = Field(min_length=1, max_length=100)

    @field_validator("public_slugs")
    @classmethod
    def _validate_public_slugs(cls, public_slugs: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(public_slugs))
        if any(
            len(slug) != 32 or any(character not in "0123456789abcdef" for character in slug) for slug in normalized
        ):
            raise ValueError("Public slugs must be 32 lowercase hexadecimal characters.")
        return normalized


class PublicationLibraryEntriesResponse(BaseModel):
    entries: dict[str, PublicationLibraryEntryResponse]


class PublicationSourceMatchResponse(BaseModel):
    match: ExploreBriefingItem | None = None
    library_entry: PublicationLibraryEntryResponse | None = None

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from fathom.schemas.briefing_sessions import BriefingSourceType

BriefingListSort = Literal["newest", "oldest"]
BriefingSourceFilter = Literal["all", "youtube", "url"]


class BriefingResponse(BaseModel):
    briefing_id: UUID
    markdown: str
    pdf_url: str | None


class BriefingPdfResponse(BaseModel):
    briefing_id: UUID
    pdf_url: str


class BriefingListItem(BaseModel):
    session_id: UUID
    briefing_id: UUID
    title: str
    author: str | None = None
    source_url: str
    source_host: str
    source_type: BriefingSourceType
    created_at: datetime
    duration_seconds: int | None = None
    session_path: str


class BriefingListResponse(BaseModel):
    items: list[BriefingListItem]
    total_count: int
    limit: int
    offset: int
    has_more: bool
    query: str | None = None
    sort: BriefingListSort
    source_type: BriefingSourceFilter

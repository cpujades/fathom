from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, HttpUrl

BriefingSessionState = Literal[
    "accepted",
    "resolving_source",
    "reusing_existing",
    "transcribing",
    "drafting_briefing",
    "finalizing_briefing",
    "ready",
    "failed",
]
BriefingSessionResolution = Literal["new", "joined_existing", "reused_ready"]
BriefingSourceType = Literal["youtube", "url"]


class BriefingSessionCreateRequest(BaseModel):
    url: HttpUrl


class BriefingSessionResponse(BaseModel):
    session_id: UUID
    briefing_id: UUID | None = None
    state: BriefingSessionState
    message: str
    detail: str | None = None
    progress: int
    resolution_type: BriefingSessionResolution
    submitted_url: str
    canonical_source_url: str
    source_type: BriefingSourceType
    source_identity_key: str
    source_title: str
    source_author: str | None = None
    source_duration_seconds: int | None = None
    source_thumbnail_url: str | None = None
    session_url: str
    events_url: str
    error_code: str | None = None
    error_message: str | None = None
    briefing_markdown: str | None = None
    briefing_has_pdf: bool = False

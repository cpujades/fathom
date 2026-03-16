from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class BriefingResponse(BaseModel):
    briefing_id: UUID
    markdown: str
    pdf_url: str | None


class BriefingPdfResponse(BaseModel):
    briefing_id: UUID
    pdf_url: str

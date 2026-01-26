from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, HttpUrl


class SummarizeRequest(BaseModel):
    url: HttpUrl


class SummarizeResponse(BaseModel):
    job_id: UUID


class SummaryResponse(BaseModel):
    summary_id: UUID
    markdown: str
    pdf_url: str | None


class SummaryPdfResponse(BaseModel):
    summary_id: UUID
    pdf_url: str

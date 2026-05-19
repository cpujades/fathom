from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DiagnosticModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    @classmethod
    def select_columns(cls) -> str:
        return ",".join(cls.model_fields)


class TimelineJob(DiagnosticModel):
    id: str
    user_id: str | None = None
    status: str | None = None
    url: str | None = None
    summary_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    stage: str | None = None
    progress: int | None = None
    status_message: str | None = None
    duration_seconds: int | None = None
    attempt_count: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    claimed_at: datetime | None = None
    last_error_at: datetime | None = None
    run_after: datetime | None = None


class TimelineSummary(DiagnosticModel):
    id: str
    user_id: str | None = None
    transcript_id: str | None = None
    prompt_key: str | None = None
    summary_model: str | None = None
    summary_markdown: str = ""
    pdf_object_key: str | None = None
    created_at: datetime | None = None
    ttl_expires_at: datetime | None = None

    @property
    def markdown_chars(self) -> int:
        return len(self.summary_markdown)


class TimelineTranscript(DiagnosticModel):
    id: str
    url_hash: str | None = None
    video_id: str | None = None
    provider_model: str | None = None
    source_title: str | None = None
    source_author: str | None = None
    source_length_seconds: int | None = None
    created_at: datetime | None = None
    ttl_expires_at: datetime | None = None


class TimelineEvent(DiagnosticModel):
    id: str | None = None
    job_id: str
    event_type: str
    stage: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class JobTimeline(DiagnosticModel):
    session_id: str
    job: TimelineJob
    summary: TimelineSummary | None = None
    transcript: TimelineTranscript | None = None
    events: list[TimelineEvent] = Field(default_factory=list)
    events_unavailable: bool = False

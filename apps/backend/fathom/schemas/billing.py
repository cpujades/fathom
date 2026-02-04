from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, HttpUrl


class CheckoutSessionRequest(BaseModel):
    plan_id: UUID


class CheckoutSessionResponse(BaseModel):
    checkout_url: HttpUrl


class PlanResponse(BaseModel):
    plan_id: UUID
    name: str
    plan_type: str
    stripe_price_id: str | None
    quota_seconds: int | None
    rollover_cap_seconds: int | None
    pack_expiry_days: int | None
    is_active: bool


class UsageOverviewResponse(BaseModel):
    subscription_plan_name: str | None
    subscription_remaining_seconds: int
    pack_remaining_seconds: int
    total_remaining_seconds: int
    pack_expires_at: datetime | None


class UsageHistoryEntry(BaseModel):
    job_id: UUID | None
    seconds_used: int
    source: str
    created_at: datetime

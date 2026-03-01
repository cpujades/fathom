from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, HttpUrl


class CheckoutSessionRequest(BaseModel):
    plan_id: UUID


class CheckoutSessionResponse(BaseModel):
    checkout_url: HttpUrl


class CustomerPortalSessionResponse(BaseModel):
    portal_url: HttpUrl


class PackRefundResponse(BaseModel):
    polar_order_id: str
    refund_id: str | None
    requested_amount_cents: int
    remaining_seconds_before_refund: int
    status: str


class PlanResponse(BaseModel):
    plan_id: UUID
    plan_code: str
    name: str
    plan_type: str
    polar_product_id: str | None
    currency: str
    amount_cents: int
    billing_interval: str | None
    version: int
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
    debt_seconds: int
    is_blocked: bool


class UsageHistoryEntry(BaseModel):
    job_id: UUID | None
    seconds_used: int
    source: str
    created_at: datetime


class SubscriptionBillingState(BaseModel):
    plan_name: str | None
    status: str | None
    period_start: datetime | None
    period_end: datetime | None


class PackBillingState(BaseModel):
    polar_order_id: str
    plan_name: str | None
    status: str
    currency: str
    paid_amount_cents: int
    refunded_amount_cents: int
    granted_seconds: int
    consumed_seconds: int
    remaining_seconds: int
    expires_at: datetime | None
    refundable_amount_cents: int
    is_refundable: bool
    created_at: datetime


class BillingOrderHistoryEntry(BaseModel):
    polar_order_id: str
    plan_name: str | None
    plan_type: str
    status: str
    currency: str
    paid_amount_cents: int
    refunded_amount_cents: int
    created_at: datetime


class BillingAccountResponse(BaseModel):
    subscription: SubscriptionBillingState
    packs: list[PackBillingState]
    orders: list[BillingOrderHistoryEntry]

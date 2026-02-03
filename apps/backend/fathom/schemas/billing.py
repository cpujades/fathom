from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, HttpUrl


class CheckoutSessionRequest(BaseModel):
    plan_id: UUID


class CheckoutSessionResponse(BaseModel):
    checkout_url: HttpUrl

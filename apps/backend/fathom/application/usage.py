from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fathom.core.config import Settings
from fathom.core.errors import ExternalServiceError, InvalidRequestError
from fathom.core.logging import log_context
from fathom.crud.supabase.billing import (
    fetch_entitlement,
    fetch_plan_by_id,
    fetch_plan_by_price_id,
    fetch_usage_entries,
    fetch_usage_history,
    insert_usage_entry,
    update_pack_balance,
    upsert_subscription_entitlement,
)
from fathom.services.supabase import create_supabase_admin_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsageSnapshot:
    subscription_remaining: int
    pack_remaining: int
    total_remaining: int
    pack_expires_at: datetime | None


@dataclass(frozen=True)
class UsageOverview:
    subscription_plan_name: str | None
    subscription_remaining: int
    pack_remaining: int
    total_remaining: int
    pack_expires_at: datetime | None


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed
        except ValueError:
            return None
    return None


async def _ensure_free_entitlement(admin_client: Any, user_id: str) -> dict[str, Any]:
    free_plan = await fetch_plan_by_price_id(admin_client, "internal_free")
    now = datetime.now(UTC)
    period_start = now
    period_end = now + timedelta(days=30)
    await upsert_subscription_entitlement(
        admin_client,
        user_id=user_id,
        plan=free_plan,
        status="active",
        period_start=period_start,
        period_end=period_end,
        existing=None,
    )
    entitlement = await fetch_entitlement(admin_client, user_id)
    if not entitlement:
        raise ExternalServiceError("Failed to initialize free tier entitlements.")
    return entitlement


async def get_usage_snapshot(
    user_id: str,
    settings: Settings,
    *,
    admin_client: Any | None = None,
) -> UsageSnapshot:
    if admin_client is None:
        admin_client = await create_supabase_admin_client(settings)
    entitlement = await fetch_entitlement(admin_client, user_id)
    if not entitlement:
        entitlement = await _ensure_free_entitlement(admin_client, user_id)

    period_start = _parse_dt(entitlement.get("period_start"))
    period_end = _parse_dt(entitlement.get("period_end"))
    monthly_quota = entitlement.get("monthly_quota_seconds") or 0
    rollover = entitlement.get("rollover_seconds") or 0

    used_seconds = 0
    if period_start and period_end and monthly_quota:
        entries = await fetch_usage_entries(
            admin_client,
            user_id=user_id,
            source="subscription",
            start=period_start,
            end=period_end,
        )
        used_seconds = sum(int(entry.get("seconds_used") or 0) for entry in entries)

    subscription_remaining = max(int(monthly_quota + rollover - used_seconds), 0)

    pack_expires_at = _parse_dt(entitlement.get("pack_expires_at"))
    pack_remaining = int(entitlement.get("pack_seconds_available") or 0)
    now = datetime.now(UTC)
    if pack_expires_at and pack_expires_at <= now:
        pack_remaining = 0
        await update_pack_balance(admin_client, user_id=user_id, pack_seconds_available=0, pack_expires_at=None)
        pack_expires_at = None

    total_remaining = subscription_remaining + pack_remaining
    return UsageSnapshot(
        subscription_remaining=subscription_remaining,
        pack_remaining=pack_remaining,
        total_remaining=total_remaining,
        pack_expires_at=pack_expires_at,
    )


async def get_usage_overview(user_id: str, settings: Settings) -> UsageOverview:
    admin_client = await create_supabase_admin_client(settings)
    entitlement = await fetch_entitlement(admin_client, user_id)
    if not entitlement:
        entitlement = await _ensure_free_entitlement(admin_client, user_id)

    plan_name: str | None = None
    plan_id = entitlement.get("subscription_plan_id")
    if isinstance(plan_id, str):
        try:
            plan = await fetch_plan_by_id(admin_client, plan_id)
            plan_name = plan.get("name")
        except Exception:
            plan_name = None

    snapshot = await get_usage_snapshot(user_id, settings, admin_client=admin_client)
    return UsageOverview(
        subscription_plan_name=plan_name,
        subscription_remaining=snapshot.subscription_remaining,
        pack_remaining=snapshot.pack_remaining,
        total_remaining=snapshot.total_remaining,
        pack_expires_at=snapshot.pack_expires_at,
    )


async def get_usage_history(user_id: str, settings: Settings, limit: int = 50) -> list[dict[str, Any]]:
    admin_client = await create_supabase_admin_client(settings)
    return await fetch_usage_history(admin_client, user_id=user_id, limit=limit)


async def record_usage_for_job(
    *,
    user_id: str,
    job_id: str,
    duration_seconds: int | None,
    settings: Settings,
) -> None:
    if not duration_seconds or duration_seconds <= 0:
        logger.info("usage skip: missing duration", extra={"user_id": user_id, "job_id": job_id})
        return

    admin_client = await create_supabase_admin_client(settings)
    with log_context(user_id=user_id, job_id=job_id):
        snapshot = await get_usage_snapshot(user_id, settings, admin_client=admin_client)
        remaining = duration_seconds

        if snapshot.subscription_remaining > 0:
            consume = min(snapshot.subscription_remaining, remaining)
            await insert_usage_entry(
                admin_client,
                user_id=user_id,
                job_id=job_id,
                seconds_used=consume,
                source="subscription",
            )
            remaining -= consume

        if remaining > 0:
            if snapshot.pack_remaining <= 0:
                logger.info("usage overage: no pack credits remaining")
                return
            consume = min(snapshot.pack_remaining, remaining)
            await insert_usage_entry(
                admin_client,
                user_id=user_id,
                job_id=job_id,
                seconds_used=consume,
                source="pack",
            )
            new_pack_balance = snapshot.pack_remaining - consume
            await update_pack_balance(
                admin_client,
                user_id=user_id,
                pack_seconds_available=new_pack_balance,
                pack_expires_at=snapshot.pack_expires_at,
            )
            remaining -= consume

        if remaining > 0:
            logger.info("usage overage remaining", extra={"seconds": remaining})


async def ensure_usage_allowed(
    *,
    user_id: str,
    duration_seconds: int | None,
    settings: Settings,
) -> None:
    snapshot = await get_usage_snapshot(user_id, settings)
    if snapshot.total_remaining <= 0:
        raise InvalidRequestError("You have no remaining credits. Please upgrade to continue.")

    if duration_seconds and duration_seconds > snapshot.total_remaining:
        logger.info(
            "usage warning: duration exceeds remaining",
            extra={"remaining": snapshot.total_remaining, "duration_seconds": duration_seconds},
        )

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fathom.core.config import Settings
from fathom.core.errors import ExternalServiceError, InvalidRequestError
from fathom.core.logging import log_context
from fathom.crud.supabase.billing import (
    consume_credit_lots,
    fetch_entitlement,
    fetch_plan_by_id,
    fetch_plan_by_product_id,
    fetch_usage_history,
    insert_usage_entry,
    summarize_credit_lots,
    update_entitlement_snapshot,
    upsert_credit_lot,
    upsert_subscription_entitlement_state,
)
from fathom.services.supabase import create_supabase_admin_client

logger = logging.getLogger(__name__)


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


@dataclass(frozen=True)
class UsageSnapshot:
    subscription_remaining: int
    pack_remaining: int
    total_remaining: int
    pack_expires_at: datetime | None
    debt_seconds: int
    is_blocked: bool


@dataclass(frozen=True)
class UsageOverview:
    subscription_plan_name: str | None
    subscription_remaining: int
    pack_remaining: int
    total_remaining: int
    pack_expires_at: datetime | None
    debt_seconds: int
    is_blocked: bool


async def _sync_entitlement_snapshot(
    admin_client: Any,
    *,
    user_id: str,
    settings: Settings,
    debt_seconds: int,
) -> UsageSnapshot:
    now = datetime.now(UTC)
    subscription_remaining, pack_remaining, pack_expires_at = await summarize_credit_lots(
        admin_client,
        user_id=user_id,
        now=now,
    )
    blocked = debt_seconds >= settings.billing_debt_cap_seconds

    await update_entitlement_snapshot(
        admin_client,
        user_id=user_id,
        subscription_available_seconds=subscription_remaining,
        pack_available_seconds=pack_remaining,
        pack_expires_at=pack_expires_at,
        debt_seconds=debt_seconds,
        is_blocked=blocked,
        last_balance_sync_at=now,
    )

    return UsageSnapshot(
        subscription_remaining=subscription_remaining,
        pack_remaining=pack_remaining,
        total_remaining=subscription_remaining + pack_remaining,
        pack_expires_at=pack_expires_at,
        debt_seconds=debt_seconds,
        is_blocked=blocked,
    )


async def _ensure_free_entitlement(admin_client: Any, user_id: str, settings: Settings) -> dict[str, Any]:
    free_plan = await fetch_plan_by_product_id(admin_client, "internal_free")
    now = datetime.now(UTC)
    period_start = now
    period_end = now + timedelta(days=30)

    source_key = f"internal_free:{period_start.date().isoformat()}"
    await upsert_credit_lot(
        admin_client,
        user_id=user_id,
        plan_id=str(free_plan["id"]),
        lot_type="subscription_cycle",
        source_key=source_key,
        granted_seconds=int(free_plan.get("quota_seconds") or 0),
        pack_expires_at=period_end,
        status="active",
    )

    await upsert_subscription_entitlement_state(
        admin_client,
        user_id=user_id,
        subscription_plan_id=str(free_plan["id"]),
        subscription_status="active",
        period_start=period_start,
        period_end=period_end,
        subscription_cycle_grant_seconds=int(free_plan.get("quota_seconds") or 0),
        subscription_rollover_seconds=0,
        subscription_available_seconds=int(free_plan.get("quota_seconds") or 0),
    )

    await _sync_entitlement_snapshot(
        admin_client,
        user_id=user_id,
        settings=settings,
        debt_seconds=0,
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
        entitlement = await _ensure_free_entitlement(admin_client, user_id, settings)

    subscription_remaining = int(entitlement.get("subscription_available_seconds") or 0)
    pack_remaining = int(entitlement.get("pack_available_seconds") or 0)
    debt_seconds = int(entitlement.get("debt_seconds") or 0)
    is_blocked = bool(entitlement.get("is_blocked"))

    return UsageSnapshot(
        subscription_remaining=subscription_remaining,
        pack_remaining=pack_remaining,
        total_remaining=subscription_remaining + pack_remaining,
        pack_expires_at=_parse_dt(entitlement.get("pack_expires_at")),
        debt_seconds=debt_seconds,
        is_blocked=is_blocked,
    )


async def get_usage_overview(user_id: str, settings: Settings) -> UsageOverview:
    admin_client = await create_supabase_admin_client(settings)
    entitlement = await fetch_entitlement(admin_client, user_id)
    if not entitlement:
        entitlement = await _ensure_free_entitlement(admin_client, user_id, settings)

    plan_name: str | None = None
    plan_id = entitlement.get("subscription_plan_id")
    if isinstance(plan_id, str):
        try:
            plan = await fetch_plan_by_id(admin_client, plan_id)
            plan_name = str(plan.get("name") or "")
        except Exception:
            plan_name = None

    snapshot = await get_usage_snapshot(user_id, settings, admin_client=admin_client)
    return UsageOverview(
        subscription_plan_name=plan_name,
        subscription_remaining=snapshot.subscription_remaining,
        pack_remaining=snapshot.pack_remaining,
        total_remaining=snapshot.total_remaining,
        pack_expires_at=snapshot.pack_expires_at,
        debt_seconds=snapshot.debt_seconds,
        is_blocked=snapshot.is_blocked,
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
        entitlement = await fetch_entitlement(admin_client, user_id)
        if not entitlement:
            entitlement = await _ensure_free_entitlement(admin_client, user_id, settings)

        remaining = duration_seconds

        consumed_subscription = await consume_credit_lots(
            admin_client,
            user_id=user_id,
            lot_type="subscription_cycle",
            seconds_to_consume=remaining,
            now=datetime.now(UTC),
        )
        if consumed_subscription > 0:
            await insert_usage_entry(
                admin_client,
                user_id=user_id,
                job_id=job_id,
                seconds_used=consumed_subscription,
                source="subscription",
            )
            remaining -= consumed_subscription

        consumed_pack = 0
        if remaining > 0:
            consumed_pack = await consume_credit_lots(
                admin_client,
                user_id=user_id,
                lot_type="pack_order",
                seconds_to_consume=remaining,
                now=datetime.now(UTC),
            )
            if consumed_pack > 0:
                await insert_usage_entry(
                    admin_client,
                    user_id=user_id,
                    job_id=job_id,
                    seconds_used=consumed_pack,
                    source="pack",
                )
                remaining -= consumed_pack

        current_debt = int(entitlement.get("debt_seconds") or 0)
        unmet_seconds = max(remaining, 0)
        new_debt = current_debt + unmet_seconds

        await _sync_entitlement_snapshot(
            admin_client,
            user_id=user_id,
            settings=settings,
            debt_seconds=new_debt,
        )


async def ensure_usage_allowed(
    *,
    user_id: str,
    duration_seconds: int | None,
    settings: Settings,
) -> None:
    snapshot = await get_usage_snapshot(user_id, settings)
    if snapshot.is_blocked:
        raise InvalidRequestError("Your account is temporarily blocked due to negative balance. Please top up credits.")

    available_now = snapshot.subscription_remaining + snapshot.pack_remaining
    current_debt = snapshot.debt_seconds

    if duration_seconds and duration_seconds > 0:
        projected_debt = current_debt + max(duration_seconds - available_now, 0)
        if projected_debt > settings.billing_debt_cap_seconds:
            raise InvalidRequestError("Insufficient credits for this video. Please upgrade or buy a pack.")

    if duration_seconds is None and available_now <= 0 and current_debt >= settings.billing_debt_cap_seconds:
        raise InvalidRequestError("You have no remaining credits. Please upgrade to continue.")

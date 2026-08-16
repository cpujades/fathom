from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fathom.core.config import Settings
from fathom.core.constants import BILLING_DEBT_CAP_SECONDS
from fathom.core.errors import (
    BalanceBlockedError,
    ExternalServiceError,
    InsufficientVideoTimeError,
    NoVideoTimeError,
    SourceDurationUnknownError,
    UsageSettlementError,
)
from fathom.core.logging import log_context
from fathom.crud.supabase.billing import (
    adjust_entitlement_debt,
    consume_credit_lot_by_id,
    expire_active_subscription_lots,
    fetch_credit_lot_by_source,
    fetch_entitlement,
    fetch_plan_by_id,
    fetch_plan_by_product_id,
    fetch_polar_order_ids_refund_pending,
    fetch_usage_settlements,
    settle_job_usage,
    summarize_credit_lots,
    update_entitlement_snapshot,
    upsert_credit_lot,
    upsert_subscription_entitlement_state,
)
from fathom.crud.supabase.jobs import fetch_jobs_by_ids
from fathom.crud.supabase.summaries import fetch_summaries_by_ids
from fathom.crud.supabase.transcripts import fetch_transcripts_by_ids
from fathom.services.supabase import create_supabase_admin_client, managed_supabase_client

logger = logging.getLogger(__name__)

FREE_TIER_PRODUCT_ID = "internal_free"
FREE_TIER_CYCLE_DAYS = 30


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
    has_active_paid_subscription: bool
    subscription_remaining: int
    pack_remaining: int
    total_remaining: int
    pack_expires_at: datetime | None
    debt_seconds: int
    is_blocked: bool


@dataclass(frozen=True)
class UsageHistoryPage:
    entries: list[dict[str, Any]]
    limit: int
    offset: int
    has_more: bool


async def _sync_entitlement_snapshot(
    admin_client: Any,
    *,
    user_id: str,
    settings: Settings,
    debt_seconds: int,
    exclude_pack_source_keys: set[str] | None = None,
) -> UsageSnapshot:
    if exclude_pack_source_keys is None:
        refund_pending_ids = await fetch_polar_order_ids_refund_pending(admin_client, user_id)
        exclude_pack_source_keys = set(refund_pending_ids) if refund_pending_ids else None

    now = datetime.now(UTC)
    subscription_remaining, pack_remaining, pack_expires_at = await summarize_credit_lots(
        admin_client,
        user_id=user_id,
        now=now,
        exclude_pack_source_keys=exclude_pack_source_keys,
    )
    blocked = debt_seconds >= BILLING_DEBT_CAP_SECONDS

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


def _advance_cycle_start_to_now(period_start: datetime, *, now: datetime) -> datetime:
    cycle = timedelta(days=FREE_TIER_CYCLE_DAYS)
    aligned = period_start
    while aligned + cycle <= now:
        aligned += cycle
    return aligned


async def _apply_debt_paydown_for_lot(
    admin_client: Any,
    *,
    user_id: str,
    lot_id: str,
    settings: Settings,
) -> int:
    entitlement = await fetch_entitlement(admin_client, user_id)
    debt_seconds = int(entitlement.get("debt_seconds") or 0) if entitlement else 0
    if debt_seconds <= 0:
        return 0

    consumed_for_paydown = await consume_credit_lot_by_id(
        admin_client,
        lot_id=lot_id,
        seconds_to_consume=debt_seconds,
        now=datetime.now(UTC),
    )
    if consumed_for_paydown <= 0:
        return debt_seconds

    return await adjust_entitlement_debt(
        admin_client,
        user_id=user_id,
        delta_seconds=-consumed_for_paydown,
        debt_cap_seconds=BILLING_DEBT_CAP_SECONDS,
    )


async def _refresh_free_entitlement_if_needed(
    admin_client: Any,
    *,
    user_id: str,
    settings: Settings,
    entitlement: dict[str, Any],
) -> dict[str, Any]:
    subscription_plan_id = entitlement.get("subscription_plan_id")
    if not isinstance(subscription_plan_id, str) or not subscription_plan_id:
        return entitlement

    now = datetime.now(UTC)
    current_period_end = _parse_dt(entitlement.get("period_end"))
    if current_period_end and current_period_end > now:
        return entitlement

    free_plan = await fetch_plan_by_product_id(admin_client, FREE_TIER_PRODUCT_ID)
    if subscription_plan_id != str(free_plan["id"]):
        return entitlement

    period_start = _advance_cycle_start_to_now(current_period_end or now, now=now)
    period_end = period_start + timedelta(days=FREE_TIER_CYCLE_DAYS)
    source_key = f"{FREE_TIER_PRODUCT_ID}:{user_id}:{period_start.isoformat()}"
    existing_cycle_lot = await fetch_credit_lot_by_source(
        admin_client,
        lot_type="subscription_cycle",
        source_key=source_key,
    )

    await expire_active_subscription_lots(admin_client, user_id=user_id)
    lot = await upsert_credit_lot(
        admin_client,
        user_id=user_id,
        plan_id=str(free_plan["id"]),
        lot_type="subscription_cycle",
        source_key=source_key,
        granted_seconds=int(free_plan.get("quota_seconds") or 0),
        expires_at=period_end,
        status="active",
    )

    debt_seconds = int(entitlement.get("debt_seconds") or 0)
    if not existing_cycle_lot:
        debt_seconds = await _apply_debt_paydown_for_lot(
            admin_client,
            user_id=user_id,
            lot_id=str(lot["id"]),
            settings=settings,
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
        debt_seconds=debt_seconds,
    )
    refreshed = await fetch_entitlement(admin_client, user_id)
    return refreshed or entitlement


async def _ensure_free_entitlement(admin_client: Any, user_id: str, settings: Settings) -> dict[str, Any]:
    free_plan = await fetch_plan_by_product_id(admin_client, FREE_TIER_PRODUCT_ID)
    now = datetime.now(UTC)
    period_start = now
    period_end = now + timedelta(days=FREE_TIER_CYCLE_DAYS)

    source_key = f"{FREE_TIER_PRODUCT_ID}:{user_id}:{period_start.isoformat()}"
    await upsert_credit_lot(
        admin_client,
        user_id=user_id,
        plan_id=str(free_plan["id"]),
        lot_type="subscription_cycle",
        source_key=source_key,
        granted_seconds=int(free_plan.get("quota_seconds") or 0),
        expires_at=period_end,
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
        async with managed_supabase_client(await create_supabase_admin_client(settings)) as owned_client:
            return await get_usage_snapshot(
                user_id,
                settings,
                admin_client=owned_client,
            )

    entitlement = await fetch_entitlement(admin_client, user_id)
    if not entitlement:
        entitlement = await _ensure_free_entitlement(admin_client, user_id, settings)
    subscription_plan_id = entitlement.get("subscription_plan_id")
    if not isinstance(subscription_plan_id, str) or not subscription_plan_id:
        # Self-heal legacy/corrupted rows so every account always has a valid
        # baseline subscription lot for guard checks.
        entitlement = await _ensure_free_entitlement(admin_client, user_id, settings)
    entitlement = await _refresh_free_entitlement_if_needed(
        admin_client,
        user_id=user_id,
        settings=settings,
        entitlement=entitlement,
    )

    debt_seconds = int(entitlement.get("debt_seconds") or 0)
    is_blocked = bool(entitlement.get("is_blocked"))

    subscription_remaining = int(entitlement.get("subscription_available_seconds") or 0)
    pack_remaining = int(entitlement.get("pack_available_seconds") or 0)
    pack_expires_at = _parse_dt(entitlement.get("pack_expires_at"))

    # Fast path: read snapshot only. Refresh only when snapshot shows an expired pack.
    now = datetime.now(UTC)
    if pack_remaining > 0 and pack_expires_at and pack_expires_at <= now:
        return await _sync_entitlement_snapshot(
            admin_client,
            user_id=user_id,
            settings=settings,
            debt_seconds=debt_seconds,
        )

    return UsageSnapshot(
        subscription_remaining=subscription_remaining,
        pack_remaining=pack_remaining,
        total_remaining=subscription_remaining + pack_remaining,
        pack_expires_at=pack_expires_at,
        debt_seconds=debt_seconds,
        is_blocked=is_blocked,
    )


async def get_usage_overview(user_id: str, settings: Settings) -> UsageOverview:
    async with managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client:
        return await _get_usage_overview(user_id, settings, admin_client)


async def _get_usage_overview(user_id: str, settings: Settings, admin_client: Any) -> UsageOverview:
    entitlement = await fetch_entitlement(admin_client, user_id)
    if not entitlement:
        entitlement = await _ensure_free_entitlement(admin_client, user_id, settings)

    plan_name: str | None = None
    has_active_paid_subscription = False
    plan_id = entitlement.get("subscription_plan_id")
    if isinstance(plan_id, str):
        try:
            plan = await fetch_plan_by_id(admin_client, plan_id)
        except Exception:
            logger.warning(
                "billing.usage.plan_lookup_failed",
                extra={"user_id": user_id, "plan_id": plan_id},
                exc_info=True,
            )
            raise
        plan_name = str(plan.get("name") or "")
        has_active_paid_subscription = (
            entitlement.get("subscription_status") == "active"
            and plan.get("polar_product_id") != FREE_TIER_PRODUCT_ID
            and int(plan.get("amount_cents") or 0) > 0
        )

    snapshot = await get_usage_snapshot(user_id, settings, admin_client=admin_client)
    return UsageOverview(
        subscription_plan_name=plan_name,
        has_active_paid_subscription=has_active_paid_subscription,
        subscription_remaining=snapshot.subscription_remaining,
        pack_remaining=snapshot.pack_remaining,
        total_remaining=snapshot.total_remaining,
        pack_expires_at=snapshot.pack_expires_at,
        debt_seconds=snapshot.debt_seconds,
        is_blocked=snapshot.is_blocked,
    )


async def get_usage_history(
    user_id: str,
    settings: Settings,
    *,
    limit: int = 10,
    offset: int = 0,
) -> UsageHistoryPage:
    async with managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client:
        return await _get_usage_history(user_id, admin_client, limit=limit, offset=offset)


async def _get_usage_history(
    user_id: str,
    admin_client: Any,
    *,
    limit: int,
    offset: int,
) -> UsageHistoryPage:
    entries = await fetch_usage_settlements(
        admin_client,
        user_id=user_id,
        limit=limit + 1,
        offset=offset,
    )
    has_more = len(entries) > limit
    entries = entries[:limit]
    job_ids = [str(entry.get("job_id")) for entry in entries if entry.get("job_id")]
    if not job_ids:
        return UsageHistoryPage(entries=entries, limit=limit, offset=offset, has_more=has_more)

    jobs = await fetch_jobs_by_ids(admin_client, job_ids)
    summary_ids = [str(job.get("summary_id")) for job in jobs if job.get("summary_id")]
    summaries = await fetch_summaries_by_ids(admin_client, summary_ids)
    transcript_ids = [str(summary.get("transcript_id")) for summary in summaries if summary.get("transcript_id")]
    transcripts = await fetch_transcripts_by_ids(admin_client, transcript_ids)

    job_by_id = {str(job.get("id")): job for job in jobs if job.get("id")}
    summary_by_id = {str(summary.get("id")): summary for summary in summaries if summary.get("id")}
    transcript_by_id = {str(transcript.get("id")): transcript for transcript in transcripts if transcript.get("id")}

    for entry in entries:
        job_id = entry.get("job_id")
        if not job_id:
            entry["title"] = None
            entry["session_path"] = None
            continue

        job = job_by_id.get(str(job_id))
        summary_id = job.get("summary_id") if isinstance(job, dict) else None
        summary = summary_by_id.get(str(summary_id)) if summary_id else None
        transcript_id = summary.get("transcript_id") if isinstance(summary, dict) else None
        transcript = transcript_by_id.get(str(transcript_id)) if transcript_id else None
        source_title = transcript.get("source_title") if isinstance(transcript, dict) else None
        entry["title"] = str(source_title).strip() if isinstance(source_title, str) and source_title.strip() else None
        entry["session_path"] = (
            f"/app/briefings/sessions/{job_id}"
            if isinstance(job, dict) and str(job.get("status") or "") != "deleted"
            else None
        )

    return UsageHistoryPage(entries=entries, limit=limit, offset=offset, has_more=has_more)


async def record_usage_for_job(
    *,
    user_id: str,
    job_id: str,
    lease_token: str,
    duration_seconds: int | None,
    settings: Settings,
    admin_client: Any,
) -> None:
    with log_context(job_id=job_id):
        try:
            result = await settle_job_usage(
                admin_client,
                job_id=job_id,
                lease_token=lease_token,
                debt_cap_seconds=BILLING_DEBT_CAP_SECONDS,
            )
        except Exception as exc:
            if isinstance(exc, UsageSettlementError):
                raise
            raise UsageSettlementError("Usage accounting could not be finalized; retrying shortly.") from exc

        settlement = result["settlement"]
        logger.info(
            "usage.settlement.completed",
            extra={
                "resolution_type": result["resolution_type"],
                "expected_duration_seconds": duration_seconds,
                "duration_seconds": settlement.get("duration_seconds"),
                "subscription_seconds": settlement.get("subscription_seconds"),
                "pack_seconds": settlement.get("pack_seconds"),
                "debt_incurred_seconds": settlement.get("debt_incurred_seconds"),
            },
        )


async def ensure_usage_allowed(
    *,
    user_id: str,
    duration_seconds: int | None,
    settings: Settings,
) -> None:
    if duration_seconds is None or duration_seconds <= 0:
        raise SourceDurationUnknownError(
            "Talven couldn't verify this video's length safely. Try another public YouTube video."
        )

    snapshot = await get_usage_snapshot(user_id, settings)
    if snapshot.is_blocked:
        raise BalanceBlockedError(
            "Briefing creation is paused while outstanding video time is repaid.",
            details={"debt_seconds": max(snapshot.debt_seconds, 0)},
        )

    available_now = snapshot.subscription_remaining + snapshot.pack_remaining

    if available_now <= 0:
        raise NoVideoTimeError(
            "No video time remains on this account.",
            details={"available_seconds": 0},
        )

    if duration_seconds > available_now:
        raise InsufficientVideoTimeError(
            "This video needs more time than is currently available.",
            details={
                "required_seconds": duration_seconds,
                "available_seconds": available_now,
            },
        )

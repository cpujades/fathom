from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fathom.application.billing.parsing import as_str
from fathom.core.config import Settings
from fathom.crud.supabase.billing import (
    adjust_entitlement_debt,
    consume_credit_lot_by_id,
    fetch_credit_lot_by_source,
    fetch_entitlement,
    fetch_polar_order_ids_refund_pending,
    revoke_remaining_credit_lot,
    summarize_credit_lots,
    update_billing_order,
    update_entitlement_snapshot,
)


async def sync_entitlement_snapshot(
    admin_client: Any,
    *,
    user_id: str,
    settings: Settings,
    debt_seconds: int | None = None,
) -> None:
    entitlement = await fetch_entitlement(admin_client, user_id)
    effective_debt = int(entitlement.get("debt_seconds") or 0) if entitlement else 0
    if debt_seconds is not None:
        effective_debt = max(debt_seconds, 0)

    now = datetime.now(UTC)
    refund_pending_order_ids = await fetch_polar_order_ids_refund_pending(admin_client, user_id)
    exclude_pack_keys = set(refund_pending_order_ids) if refund_pending_order_ids else None
    subscription_remaining, pack_remaining, next_pack_expiry = await summarize_credit_lots(
        admin_client,
        user_id=user_id,
        now=now,
        exclude_pack_source_keys=exclude_pack_keys,
    )
    is_blocked = effective_debt >= settings.billing_debt_cap_seconds

    await update_entitlement_snapshot(
        admin_client,
        user_id=user_id,
        subscription_available_seconds=subscription_remaining,
        pack_available_seconds=pack_remaining,
        pack_expires_at=next_pack_expiry,
        debt_seconds=effective_debt,
        is_blocked=is_blocked,
        last_balance_sync_at=now,
    )


async def apply_debt_paydown_for_lot(
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
        debt_cap_seconds=settings.billing_debt_cap_seconds,
    )


async def apply_order_refund_state(
    admin_client: Any,
    *,
    order: dict[str, Any],
    settings: Settings,
    provider_total_refunded: int | None,
    refund_delta_cents: int = 0,
) -> None:
    paid_amount_cents = int(order.get("paid_amount_cents") or 0)
    existing_refunded = int(order.get("refunded_amount_cents") or 0)
    if provider_total_refunded is not None:
        new_refunded_cents = min(max(existing_refunded, provider_total_refunded), paid_amount_cents)
    else:
        new_refunded_cents = min(existing_refunded + refund_delta_cents, paid_amount_cents)

    plan_type = order.get("plan_type")
    is_pack = plan_type == "pack"
    pack_refund_completed = is_pack and new_refunded_cents > 0
    non_pack_full_refund = not is_pack and paid_amount_cents > 0 and new_refunded_cents >= paid_amount_cents
    set_refunded = pack_refund_completed or non_pack_full_refund
    current_status = as_str(order.get("status")) or "paid"
    next_status = "refunded" if set_refunded else current_status

    await update_billing_order(
        admin_client,
        order_id=str(order["id"]),
        values={
            "status": next_status,
            "refunded_amount_cents": new_refunded_cents,
        },
    )

    if is_pack and set_refunded:
        lot = await fetch_credit_lot_by_source(
            admin_client,
            lot_type="pack_order",
            source_key=str(order.get("polar_order_id") or ""),
        )
        if lot:
            await revoke_remaining_credit_lot(admin_client, lot_id=str(lot["id"]))

    user_id = as_str(order.get("user_id"))
    if user_id:
        await sync_entitlement_snapshot(
            admin_client,
            user_id=user_id,
            settings=settings,
        )

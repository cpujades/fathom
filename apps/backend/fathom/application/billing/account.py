from __future__ import annotations

from datetime import UTC, datetime

from fathom.api.deps.auth import AuthContext
from fathom.application.billing.parsing import as_str, parse_dt
from fathom.core.config import Settings
from fathom.crud.supabase.billing import (
    fetch_entitlement,
    fetch_pack_lots_by_order_ids,
    fetch_plan_names_by_ids,
    list_billing_orders_for_user,
    remaining_seconds_from_lot,
)
from fathom.schemas.billing import (
    BillingAccountResponse,
    BillingOrderHistoryEntry,
    PackBillingState,
    SubscriptionBillingState,
)
from fathom.services.supabase import create_supabase_admin_client


async def get_billing_account(
    *,
    auth: AuthContext,
    settings: Settings,
) -> BillingAccountResponse:
    admin_client = await create_supabase_admin_client(settings)
    entitlement = await fetch_entitlement(admin_client, auth.user_id)
    orders = await list_billing_orders_for_user(admin_client, user_id=auth.user_id, limit=50)

    plan_ids: set[str] = {
        str(order["plan_id"]) for order in orders if isinstance(order.get("plan_id"), str) and order.get("plan_id")
    }
    subscription_plan_id = as_str(entitlement.get("subscription_plan_id")) if entitlement else None
    if subscription_plan_id:
        plan_ids.add(subscription_plan_id)
    plan_names = await fetch_plan_names_by_ids(admin_client, plan_ids=plan_ids)

    pack_order_ids = {
        str(order["polar_order_id"])
        for order in orders
        if str(order.get("plan_type") or "") == "pack" and order.get("polar_order_id")
    }
    pack_lots = await fetch_pack_lots_by_order_ids(
        admin_client,
        user_id=auth.user_id,
        order_ids=pack_order_ids,
    )
    now = datetime.now(UTC)

    packs: list[PackBillingState] = []
    order_entries: list[BillingOrderHistoryEntry] = []
    for order in orders:
        polar_order_id = str(order.get("polar_order_id") or "")
        plan_id = as_str(order.get("plan_id"))
        plan_name = plan_names.get(plan_id) if plan_id else None
        plan_type = str(order.get("plan_type") or "unknown")
        status = as_str(order.get("status")) or "unknown"
        currency = as_str(order.get("currency")) or "usd"
        paid_amount_cents = int(order.get("paid_amount_cents") or 0)
        refunded_amount_cents = int(order.get("refunded_amount_cents") or 0)
        created_at = parse_dt(order.get("created_at")) or now

        order_entries.append(
            BillingOrderHistoryEntry(
                polar_order_id=polar_order_id,
                plan_name=plan_name,
                plan_type=plan_type,
                status=status,
                currency=currency,
                paid_amount_cents=paid_amount_cents,
                refunded_amount_cents=refunded_amount_cents,
                created_at=created_at,
            )
        )

        if plan_type != "pack":
            continue

        lot = pack_lots.get(polar_order_id)
        granted_seconds = int(lot.get("granted_seconds") or 0) if lot else 0
        consumed_seconds = int(lot.get("consumed_seconds") or 0) if lot else 0
        expires_at = parse_dt(lot.get("pack_expires_at")) if lot else None
        remaining_seconds = 0
        if lot and (not expires_at or expires_at > now):
            remaining_seconds = remaining_seconds_from_lot(lot)

        refundable_amount_cents = 0
        if status == "paid" and granted_seconds > 0 and remaining_seconds > 0 and paid_amount_cents > 0:
            refundable_amount_cents = (paid_amount_cents * remaining_seconds) // granted_seconds
        is_refundable = status == "paid" and refundable_amount_cents > 0

        packs.append(
            PackBillingState(
                polar_order_id=polar_order_id,
                plan_name=plan_name,
                status=status,
                currency=currency,
                paid_amount_cents=paid_amount_cents,
                refunded_amount_cents=refunded_amount_cents,
                granted_seconds=granted_seconds,
                consumed_seconds=consumed_seconds,
                remaining_seconds=remaining_seconds,
                expires_at=expires_at,
                refundable_amount_cents=refundable_amount_cents,
                is_refundable=is_refundable,
                created_at=created_at,
            )
        )

    return BillingAccountResponse(
        subscription=SubscriptionBillingState(
            plan_name=plan_names.get(subscription_plan_id) if subscription_plan_id else None,
            status=as_str(entitlement.get("subscription_status")) if entitlement else None,
            period_start=parse_dt(entitlement.get("period_start")) if entitlement else None,
            period_end=parse_dt(entitlement.get("period_end")) if entitlement else None,
        ),
        packs=packs,
        orders=order_entries,
    )

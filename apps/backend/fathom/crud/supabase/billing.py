from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from postgrest import APIError
from postgrest.types import CountMethod, ReturnMethod

from fathom.core.errors import ExternalServiceError
from fathom.services.supabase.helpers import first_row, raise_for_postgrest_error
from supabase import AsyncClient

PLAN_SELECT_FIELDS = (
    "id,name,plan_code,plan_type,polar_product_id,currency,amount_cents,billing_interval,version,"
    "quota_seconds,rollover_cap_seconds,pack_expiry_days,is_active"
)

ORDER_SELECT_FIELDS = (
    "id,polar_order_id,user_id,plan_id,plan_type,polar_product_id,polar_subscription_id,"
    "currency,paid_amount_cents,refunded_amount_cents,status,created_at,updated_at"
)

LOT_SELECT_FIELDS = (
    "id,user_id,plan_id,lot_type,source_key,granted_seconds,consumed_seconds,revoked_seconds,"
    "pack_expires_at,status,created_at,updated_at"
)

ENTITLEMENT_SELECT_FIELDS = (
    "user_id,subscription_plan_id,subscription_status,period_start,period_end,"
    "subscription_cycle_grant_seconds,subscription_rollover_seconds,subscription_available_seconds,"
    "pack_available_seconds,pack_expires_at,debt_seconds,is_blocked,last_balance_sync_at"
)


async def fetch_plan_by_id(client: AsyncClient, plan_id: str) -> dict[str, Any]:
    try:
        response = await client.table("plans").select(PLAN_SELECT_FIELDS).eq("id", plan_id).limit(1).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch plan.")

    return first_row(
        response.data,
        error_message="Supabase returned an unexpected plans shape.",
        not_found_message="Plan not found.",
    )


async def fetch_plan_by_product_id(client: AsyncClient, product_id: str) -> dict[str, Any]:
    try:
        response = (
            await client.table("plans").select(PLAN_SELECT_FIELDS).eq("polar_product_id", product_id).limit(1).execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch plan by product id.")

    return first_row(
        response.data,
        error_message="Supabase returned an unexpected plans shape.",
        not_found_message="Plan not found for Polar product id.",
    )


async def fetch_active_plans(client: AsyncClient) -> list[dict[str, Any]]:
    try:
        response = (
            await client.table("plans")
            .select(PLAN_SELECT_FIELDS)
            .eq("is_active", True)
            .order("plan_type", desc=False)
            .order("amount_cents", desc=False)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch plans.")

    data = response.data or []
    return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]


async def upsert_polar_customer(
    client: AsyncClient,
    *,
    user_id: str,
    external_customer_id: str,
    polar_customer_id: str | None = None,
    email: str | None = None,
    country: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "user_id": user_id,
        "external_customer_id": external_customer_id,
    }
    if polar_customer_id:
        payload["polar_customer_id"] = polar_customer_id
    if email is not None:
        payload["email"] = email
    if country is not None:
        payload["country"] = country

    try:
        await client.table("polar_customers").upsert(payload, on_conflict="user_id").execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to upsert Polar customer.")


async def record_webhook_event_received(
    client: AsyncClient,
    *,
    event_id: str,
    provider: str,
    event_type: str,
    payload: dict[str, Any],
) -> bool:
    try:
        await (
            client.table("billing_webhook_events")
            .insert(
                {
                    "event_id": event_id,
                    "provider": provider,
                    "event_type": event_type,
                    "payload": payload,
                    "status": "received",
                }
            )
            .execute()
        )
    except APIError as exc:
        if (getattr(exc, "code", None) or "") == "23505":
            return False
        raise_for_postgrest_error(exc, "Failed to record webhook event.")

    return True


async def claim_webhook_event_for_processing(client: AsyncClient, *, event_id: str) -> bool:
    """Claim an event for processing by transitioning it from received or failed to processing.
    Only received/failed rows are updated; in-flight (processing) rows are left alone so a
    duplicate delivery cannot steal the event and cause double processing. Stale processing
    events should be reclaimed by a separate scheduled job, not in the webhook request path.
    """
    try:
        response = (
            await client.table("billing_webhook_events")
            .update(
                {
                    "status": "processing",
                    "processed_at": None,
                    "error": None,
                },
                count=CountMethod.exact,
                returning=ReturnMethod.minimal,
            )
            .eq("event_id", event_id)
            .in_("status", ["received", "failed"])
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to claim webhook event for processing.")

    return int(response.count or 0) > 0


async def mark_webhook_event_processed(client: AsyncClient, event_id: str) -> None:
    try:
        await (
            client.table("billing_webhook_events")
            .update(
                {
                    "status": "processed",
                    "processed_at": datetime.now(UTC).isoformat(),
                    "error": None,
                }
            )
            .eq("event_id", event_id)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to mark webhook event as processed.")


async def mark_webhook_event_failed(client: AsyncClient, event_id: str, error: str) -> None:
    try:
        await (
            client.table("billing_webhook_events")
            .update(
                {
                    "status": "failed",
                    "processed_at": datetime.now(UTC).isoformat(),
                    "error": error[:1000],
                }
            )
            .eq("event_id", event_id)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to mark webhook event as failed.")


async def upsert_billing_order(
    client: AsyncClient,
    *,
    polar_order_id: str,
    user_id: str,
    plan_id: str | None,
    plan_type: str,
    polar_product_id: str | None,
    polar_subscription_id: str | None,
    currency: str,
    paid_amount_cents: int,
    status: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "polar_order_id": polar_order_id,
        "user_id": user_id,
        "plan_id": plan_id,
        "plan_type": plan_type,
        "polar_product_id": polar_product_id,
        "polar_subscription_id": polar_subscription_id,
        "currency": currency.lower(),
        "paid_amount_cents": paid_amount_cents,
        "status": status,
    }

    try:
        response = await client.table("billing_orders").upsert(payload, on_conflict="polar_order_id").execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to upsert billing order.")

    data = response.data or []
    if not data or not isinstance(data[0], dict):
        raise ExternalServiceError("Supabase did not return billing order data after upsert.")
    return cast(dict[str, Any], data[0])


async def fetch_billing_order_by_polar_id(client: AsyncClient, polar_order_id: str) -> dict[str, Any] | None:
    try:
        response = (
            await client.table("billing_orders")
            .select(ORDER_SELECT_FIELDS)
            .eq("polar_order_id", polar_order_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch billing order by Polar id.")

    data = response.data or []
    if not data:
        return None
    return cast(dict[str, Any], data[0])


async def fetch_billing_order_for_user(
    client: AsyncClient,
    *,
    user_id: str,
    polar_order_id: str,
) -> dict[str, Any] | None:
    try:
        response = (
            await client.table("billing_orders")
            .select(ORDER_SELECT_FIELDS)
            .eq("user_id", user_id)
            .eq("polar_order_id", polar_order_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch billing order for user.")

    data = response.data or []
    if not data:
        return None
    return cast(dict[str, Any], data[0])


async def fetch_polar_order_ids_refund_pending(client: AsyncClient, user_id: str) -> list[str]:
    try:
        response = (
            await client.table("billing_orders")
            .select("polar_order_id")
            .eq("user_id", user_id)
            .eq("status", "refund_pending")
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch refund-pending orders.")

    data = response.data or []
    return [str(row["polar_order_id"]) for row in data if isinstance(row, dict) and row.get("polar_order_id")]


async def update_billing_order(
    client: AsyncClient,
    *,
    order_id: str,
    values: dict[str, Any],
) -> None:
    try:
        await client.table("billing_orders").update(values).eq("id", order_id).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to update billing order.")


async def transition_billing_order_status(
    client: AsyncClient,
    *,
    order_id: str,
    from_status: str,
    to_status: str,
) -> bool:
    try:
        response = (
            await client.table("billing_orders")
            .update(
                {"status": to_status},
                count=CountMethod.exact,
                returning=ReturnMethod.minimal,
            )
            .eq("id", order_id)
            .eq("status", from_status)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to transition billing order status.")

    return int(response.count or 0) > 0


async def upsert_credit_lot(
    client: AsyncClient,
    *,
    user_id: str,
    plan_id: str | None,
    lot_type: str,
    source_key: str,
    granted_seconds: int,
    pack_expires_at: datetime | None,
    status: str = "active",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "user_id": user_id,
        "plan_id": plan_id,
        "lot_type": lot_type,
        "source_key": source_key,
        "granted_seconds": granted_seconds,
        "pack_expires_at": pack_expires_at.isoformat() if pack_expires_at else None,
        "status": status,
    }

    try:
        response = await client.table("credit_lots").upsert(payload, on_conflict="lot_type,source_key").execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to upsert credit lot.")

    data = response.data or []
    if not data or not isinstance(data[0], dict):
        raise ExternalServiceError("Supabase did not return credit lot data after upsert.")
    return cast(dict[str, Any], data[0])


async def fetch_credit_lot_by_source(
    client: AsyncClient,
    *,
    lot_type: str,
    source_key: str,
) -> dict[str, Any] | None:
    try:
        response = (
            await client.table("credit_lots")
            .select(LOT_SELECT_FIELDS)
            .eq("lot_type", lot_type)
            .eq("source_key", source_key)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch credit lot by source.")

    data = response.data or []
    if not data:
        return None
    return cast(dict[str, Any], data[0])


async def fetch_credit_lot_by_id(client: AsyncClient, lot_id: str) -> dict[str, Any] | None:
    try:
        response = await client.table("credit_lots").select(LOT_SELECT_FIELDS).eq("id", lot_id).limit(1).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch credit lot by id.")

    data = response.data or []
    if not data:
        return None
    return cast(dict[str, Any], data[0])


async def update_credit_lot(
    client: AsyncClient,
    *,
    lot_id: str,
    values: dict[str, Any],
) -> None:
    try:
        await client.table("credit_lots").update(values).eq("id", lot_id).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to update credit lot.")


async def _compare_and_update_credit_lot(
    client: AsyncClient,
    *,
    lot_id: str,
    expected_consumed_seconds: int,
    expected_revoked_seconds: int,
    expected_status: str,
    values: dict[str, Any],
) -> bool:
    try:
        response = (
            await client.table("credit_lots")
            .update(
                values,
                count=CountMethod.exact,
                returning=ReturnMethod.minimal,
            )
            .eq("id", lot_id)
            .eq("consumed_seconds", expected_consumed_seconds)
            .eq("revoked_seconds", expected_revoked_seconds)
            .eq("status", expected_status)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to atomically update credit lot.")

    return int(response.count or 0) > 0


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def remaining_seconds_from_lot(lot: dict[str, Any]) -> int:
    granted = int(lot.get("granted_seconds") or 0)
    consumed = int(lot.get("consumed_seconds") or 0)
    revoked = int(lot.get("revoked_seconds") or 0)
    return max(granted - consumed - revoked, 0)


async def list_credit_lots_for_consumption(
    client: AsyncClient,
    *,
    user_id: str,
    lot_type: str,
    now: datetime,
    exclude_pack_source_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    try:
        response = (
            await client.table("credit_lots")
            .select(LOT_SELECT_FIELDS)
            .eq("user_id", user_id)
            .eq("lot_type", lot_type)
            .eq("status", "active")
            .order("pack_expires_at", desc=False)
            .order("created_at", desc=False)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch credit lots for consumption.")

    rows = [cast(dict[str, Any], row) for row in (response.data or []) if isinstance(row, dict)]
    if lot_type == "pack_order" and exclude_pack_source_keys:
        rows = [r for r in rows if str(r.get("source_key") or "") not in exclude_pack_source_keys]
    lots: list[dict[str, Any]] = []
    for row in rows:
        expiry = _parse_timestamp(row.get("pack_expires_at"))
        if expiry and expiry <= now:
            # Keep expired lots out of runtime accounting reads.
            await update_credit_lot(
                client,
                lot_id=str(row["id"]),
                values={"status": "expired"},
            )
            continue

        remaining = remaining_seconds_from_lot(row)
        if remaining <= 0:
            continue

        row["remaining_seconds"] = remaining
        lots.append(row)

    return lots


async def consume_credit_lots(
    client: AsyncClient,
    *,
    user_id: str,
    lot_type: str,
    seconds_to_consume: int,
    now: datetime,
    exclude_pack_source_keys: set[str] | None = None,
) -> int:
    if seconds_to_consume <= 0:
        return 0

    lots = await list_credit_lots_for_consumption(
        client,
        user_id=user_id,
        lot_type=lot_type,
        now=now,
        exclude_pack_source_keys=exclude_pack_source_keys,
    )
    remaining = seconds_to_consume
    consumed_total = 0

    for lot in lots:
        if remaining <= 0:
            break
        consumed = await consume_credit_lot_by_id(
            client,
            lot_id=str(lot["id"]),
            seconds_to_consume=remaining,
            now=now,
        )
        if consumed <= 0:
            continue
        consumed_total += consumed
        remaining -= consumed

    return consumed_total


async def consume_credit_lot_by_id(
    client: AsyncClient,
    *,
    lot_id: str,
    seconds_to_consume: int,
    now: datetime,
    max_retries: int = 5,
) -> int:
    if seconds_to_consume <= 0:
        return 0

    lot = await fetch_credit_lot_by_id(client, lot_id)
    for _ in range(max_retries):
        if not lot:
            return 0

        status = str(lot.get("status") or "")
        if status != "active":
            return 0

        expiry = _parse_timestamp(lot.get("pack_expires_at"))
        if expiry and expiry <= now:
            consumed = int(lot.get("consumed_seconds") or 0)
            revoked = int(lot.get("revoked_seconds") or 0)
            await _compare_and_update_credit_lot(
                client,
                lot_id=lot_id,
                expected_consumed_seconds=consumed,
                expected_revoked_seconds=revoked,
                expected_status="active",
                values={"status": "expired"},
            )
            return 0

        granted = int(lot.get("granted_seconds") or 0)
        consumed = int(lot.get("consumed_seconds") or 0)
        revoked = int(lot.get("revoked_seconds") or 0)
        remaining = max(granted - consumed - revoked, 0)
        if remaining <= 0:
            return 0

        consume = min(remaining, seconds_to_consume)
        updated = await _compare_and_update_credit_lot(
            client,
            lot_id=lot_id,
            expected_consumed_seconds=consumed,
            expected_revoked_seconds=revoked,
            expected_status="active",
            values={"consumed_seconds": consumed + consume},
        )
        if updated:
            return consume

        lot = await fetch_credit_lot_by_id(client, lot_id)

    return 0


async def revoke_remaining_credit_lot(client: AsyncClient, *, lot_id: str) -> int:
    lot = await fetch_credit_lot_by_id(client, lot_id)
    for _ in range(5):
        if not lot:
            return 0

        status = str(lot.get("status") or "")
        consumed = int(lot.get("consumed_seconds") or 0)
        revoked = int(lot.get("revoked_seconds") or 0)
        granted = int(lot.get("granted_seconds") or 0)
        remaining = max(granted - consumed - revoked, 0)
        if remaining <= 0:
            if status == "active":
                await _compare_and_update_credit_lot(
                    client,
                    lot_id=lot_id,
                    expected_consumed_seconds=consumed,
                    expected_revoked_seconds=revoked,
                    expected_status="active",
                    values={"status": "revoked"},
                )
            return 0

        updated = await _compare_and_update_credit_lot(
            client,
            lot_id=lot_id,
            expected_consumed_seconds=consumed,
            expected_revoked_seconds=revoked,
            expected_status="active",
            values={
                "revoked_seconds": revoked + remaining,
                "status": "revoked",
            },
        )
        if updated:
            return remaining

        lot = await fetch_credit_lot_by_id(client, lot_id)

    return 0


async def expire_active_subscription_lots(client: AsyncClient, *, user_id: str) -> None:
    try:
        await (
            client.table("credit_lots")
            .update({"status": "expired"})
            .eq("user_id", user_id)
            .eq("lot_type", "subscription_cycle")
            .eq("status", "active")
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to expire active subscription lots.")


async def summarize_credit_lots(
    client: AsyncClient,
    *,
    user_id: str,
    now: datetime,
) -> tuple[int, int, datetime | None]:
    try:
        response = (
            await client.table("credit_lots")
            .select(LOT_SELECT_FIELDS)
            .eq("user_id", user_id)
            .eq("status", "active")
            .in_("lot_type", ["subscription_cycle", "pack_order"])
            .order("pack_expires_at", desc=False)
            .order("created_at", desc=False)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to summarize credit lots.")

    rows = [cast(dict[str, Any], row) for row in (response.data or []) if isinstance(row, dict)]
    subscription_remaining = 0
    pack_remaining = 0
    next_pack_expiry: datetime | None = None

    for row in rows:
        expiry = _parse_timestamp(row.get("pack_expires_at"))
        if expiry and expiry <= now:
            await update_credit_lot(
                client,
                lot_id=str(row["id"]),
                values={"status": "expired"},
            )
            continue

        remaining = remaining_seconds_from_lot(row)
        if remaining <= 0:
            continue

        lot_type = str(row.get("lot_type") or "")
        if lot_type == "subscription_cycle":
            subscription_remaining += remaining
            continue

        if lot_type == "pack_order":
            pack_remaining += remaining
            if expiry and (next_pack_expiry is None or expiry < next_pack_expiry):
                next_pack_expiry = expiry

    return subscription_remaining, pack_remaining, next_pack_expiry


async def fetch_entitlement(client: AsyncClient, user_id: str) -> dict[str, Any] | None:
    try:
        response = (
            await client.table("entitlements")
            .select(ENTITLEMENT_SELECT_FIELDS)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch entitlements.")

    data = response.data or []
    if not data:
        return None
    return cast(dict[str, Any], data[0])


async def upsert_subscription_entitlement_state(
    client: AsyncClient,
    *,
    user_id: str,
    subscription_plan_id: str | None,
    subscription_status: str,
    period_start: datetime | None,
    period_end: datetime | None,
    subscription_cycle_grant_seconds: int,
    subscription_rollover_seconds: int,
    subscription_available_seconds: int,
) -> None:
    payload: dict[str, Any] = {
        "user_id": user_id,
        "subscription_plan_id": subscription_plan_id,
        "subscription_status": subscription_status,
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "subscription_cycle_grant_seconds": subscription_cycle_grant_seconds,
        "subscription_rollover_seconds": subscription_rollover_seconds,
        "subscription_available_seconds": subscription_available_seconds,
    }

    try:
        await client.table("entitlements").upsert(payload).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to upsert subscription entitlement state.")


async def update_entitlement_snapshot(
    client: AsyncClient,
    *,
    user_id: str,
    subscription_available_seconds: int,
    pack_available_seconds: int,
    pack_expires_at: datetime | None,
    debt_seconds: int,
    is_blocked: bool,
    last_balance_sync_at: datetime,
) -> None:
    payload: dict[str, Any] = {
        "user_id": user_id,
        "subscription_available_seconds": subscription_available_seconds,
        "pack_available_seconds": pack_available_seconds,
        "pack_expires_at": pack_expires_at.isoformat() if pack_expires_at else None,
        "debt_seconds": debt_seconds,
        "is_blocked": is_blocked,
        "last_balance_sync_at": last_balance_sync_at.isoformat(),
    }

    try:
        await client.table("entitlements").upsert(payload).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to update entitlement snapshot.")


async def adjust_entitlement_debt(
    client: AsyncClient,
    *,
    user_id: str,
    delta_seconds: int,
    debt_cap_seconds: int,
    max_retries: int = 5,
) -> int:
    if delta_seconds == 0:
        entitlement = await fetch_entitlement(client, user_id)
        return int(entitlement.get("debt_seconds") or 0) if entitlement else 0

    for _ in range(max_retries):
        entitlement = await fetch_entitlement(client, user_id)
        if not entitlement:
            await client.table("entitlements").upsert({"user_id": user_id}).execute()
            entitlement = await fetch_entitlement(client, user_id)
            if not entitlement:
                continue

        current_debt = int(entitlement.get("debt_seconds") or 0)
        new_debt = max(current_debt + delta_seconds, 0)
        payload: dict[str, Any] = {
            "debt_seconds": new_debt,
            "is_blocked": new_debt >= debt_cap_seconds,
            "last_balance_sync_at": datetime.now(UTC).isoformat(),
        }
        try:
            response = (
                await client.table("entitlements")
                .update(
                    payload,
                    count=CountMethod.exact,
                    returning=ReturnMethod.minimal,
                )
                .eq("user_id", user_id)
                .eq("debt_seconds", current_debt)
                .execute()
            )
        except APIError as exc:
            raise_for_postgrest_error(exc, "Failed to adjust entitlement debt.")

        if int(response.count or 0) > 0:
            return new_debt

    raise ExternalServiceError("Failed to adjust entitlement debt due to concurrent updates.")


async def fetch_usage_history(
    client: AsyncClient,
    *,
    user_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    try:
        response = (
            await client.table("usage_ledger")
            .select("job_id,seconds_used,source,created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch usage history.")

    data = response.data or []
    return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]


async def insert_usage_entry(
    client: AsyncClient,
    *,
    user_id: str,
    job_id: str | None,
    seconds_used: int,
    source: str,
) -> None:
    payload: dict[str, Any] = {
        "user_id": user_id,
        "seconds_used": seconds_used,
        "source": source,
    }
    if job_id:
        payload["job_id"] = job_id
    try:
        await client.table("usage_ledger").insert(payload).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to insert usage ledger entry.")

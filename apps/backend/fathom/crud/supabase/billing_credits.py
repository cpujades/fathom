from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from postgrest import APIError
from postgrest.types import CountMethod, ReturnMethod

from fathom.core.errors import ExternalServiceError
from fathom.services.supabase.helpers import raise_for_postgrest_error
from supabase import AsyncClient

LOT_SELECT_FIELDS = (
    "id,user_id,plan_id,lot_type,source_key,granted_seconds,consumed_seconds,revoked_seconds,"
    "expires_at,status,created_at,updated_at"
)


async def fetch_pack_lots_by_order_ids(
    client: AsyncClient,
    *,
    user_id: str,
    order_ids: set[str],
) -> dict[str, dict[str, Any]]:
    if not order_ids:
        return {}

    try:
        response = (
            await client.table("credit_lots")
            .select(LOT_SELECT_FIELDS)
            .eq("user_id", user_id)
            .eq("lot_type", "pack_order")
            .in_("source_key", list(order_ids))
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch pack lots by order ids.")

    rows = [cast(dict[str, Any], row) for row in (response.data or []) if isinstance(row, dict)]
    return {str(row["source_key"]): row for row in rows if row.get("source_key")}


async def upsert_credit_lot(
    client: AsyncClient,
    *,
    user_id: str,
    plan_id: str | None,
    lot_type: str,
    source_key: str,
    granted_seconds: int,
    expires_at: datetime | None,
    status: str = "active",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "user_id": user_id,
        "plan_id": plan_id,
        "lot_type": lot_type,
        "source_key": source_key,
        "granted_seconds": granted_seconds,
        "expires_at": expires_at.isoformat() if expires_at else None,
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
            .update(values, count=CountMethod.exact, returning=ReturnMethod.minimal)
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
        if not lot or str(lot.get("status") or "") != "active":
            return 0

        expiry = _parse_timestamp(lot.get("expires_at"))
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
    exclude_pack_source_keys: set[str] | None = None,
) -> tuple[int, int, datetime | None]:
    try:
        response = (
            await client.table("credit_lots")
            .select(LOT_SELECT_FIELDS)
            .eq("user_id", user_id)
            .eq("status", "active")
            .in_("lot_type", ["subscription_cycle", "pack_order"])
            .order("expires_at", desc=False)
            .order("created_at", desc=False)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to summarize credit lots.")

    rows = [cast(dict[str, Any], row) for row in (response.data or []) if isinstance(row, dict)]
    if exclude_pack_source_keys:
        rows = [
            row
            for row in rows
            if str(row.get("lot_type") or "") != "pack_order"
            or str(row.get("source_key") or "") not in exclude_pack_source_keys
        ]
    subscription_remaining = 0
    pack_remaining = 0
    next_pack_expiry: datetime | None = None

    for row in rows:
        expiry = _parse_timestamp(row.get("expires_at"))
        if expiry and expiry <= now:
            await update_credit_lot(client, lot_id=str(row["id"]), values={"status": "expired"})
            continue

        remaining = remaining_seconds_from_lot(row)
        if remaining <= 0:
            continue

        lot_type = str(row.get("lot_type") or "")
        if lot_type == "subscription_cycle":
            subscription_remaining += remaining
        elif lot_type == "pack_order":
            pack_remaining += remaining
            if expiry and (next_pack_expiry is None or expiry < next_pack_expiry):
                next_pack_expiry = expiry

    return subscription_remaining, pack_remaining, next_pack_expiry

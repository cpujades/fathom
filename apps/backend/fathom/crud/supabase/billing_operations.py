from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import uuid4

from postgrest import APIError

from fathom.core.errors import ExternalServiceError
from fathom.services.supabase.helpers import raise_for_postgrest_error, response_records
from supabase import AsyncClient

BILLING_OPERATION_TTL = timedelta(hours=24)
OPERATION_SELECT_FIELDS = "id,operation_type,status,failure_code,created_at,updated_at"
BillingOperationResolution = Literal[
    "resolved",
    "already_resolved",
    "not_found",
    "correlation_mismatch",
    "terminal_mismatch",
    "invalid_transition",
]
_BILLING_OPERATION_RESOLUTIONS = frozenset(BillingOperationResolution.__args__)


async def create_billing_sync_operation(
    client: AsyncClient,
    *,
    user_id: str,
    operation_type: str,
    plan_id: str | None = None,
    polar_order_id: str | None = None,
) -> str:
    operation_id = str(uuid4())
    try:
        await (
            client.table("billing_sync_operations")
            .insert(
                {
                    "id": operation_id,
                    "user_id": user_id,
                    "operation_type": operation_type,
                    "plan_id": plan_id,
                    "polar_order_id": polar_order_id,
                    "expires_at": (datetime.now(UTC) + BILLING_OPERATION_TTL).isoformat(),
                }
            )
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to create billing sync operation.")
    return operation_id


async def fetch_billing_sync_operation(
    client: AsyncClient,
    *,
    operation_id: str,
    user_id: str,
) -> dict[str, Any] | None:
    try:
        response = (
            await client.table("billing_sync_operations")
            .select(OPERATION_SELECT_FIELDS)
            .eq("id", operation_id)
            .eq("user_id", user_id)
            .gt("expires_at", datetime.now(UTC).isoformat())
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch billing sync operation.")

    records = response_records(
        response.data,
        error_message="Supabase returned an unexpected billing sync operation shape.",
    )
    return records[0] if records else None


async def resolve_billing_sync_operation(
    client: AsyncClient,
    *,
    operation_id: str,
    status: str,
    failure_code: str | None = None,
    user_id: str,
    operation_type: str,
    plan_id: str | None = None,
    polar_order_id: str | None = None,
) -> BillingOperationResolution:
    try:
        response = await client.rpc(
            "resolve_billing_sync_operation",
            {
                "p_operation_id": operation_id,
                "p_user_id": user_id,
                "p_operation_type": operation_type,
                "p_status": status,
                "p_failure_code": failure_code,
                "p_plan_id": plan_id,
                "p_polar_order_id": polar_order_id,
            },
        ).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to resolve billing sync operation.")

    resolution = response.data
    if not isinstance(resolution, str) or resolution not in _BILLING_OPERATION_RESOLUTIONS:
        raise ExternalServiceError("Supabase returned an unexpected billing operation resolution.")
    return cast(BillingOperationResolution, resolution)


async def resolve_refund_sync_operations(
    client: AsyncClient,
    *,
    polar_order_id: str,
    status: str,
    failure_code: str | None = None,
) -> int:
    try:
        response = await (
            client.table("billing_sync_operations")
            .update({"status": status, "failure_code": failure_code})
            .eq("operation_type", "refund")
            .eq("polar_order_id", polar_order_id)
            .in_("status", ["pending", status])
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to resolve refund sync operation.")

    records = response_records(
        response.data,
        error_message="Supabase returned an unexpected refund operation resolution shape.",
    )
    return len(records)

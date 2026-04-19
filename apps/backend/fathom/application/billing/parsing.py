from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from fathom.core.errors import InvalidRequestError

WEBHOOK_ID_HEADERS = ("webhook-id", "svix-id")
FREE_TIER_PRODUCT_ID = "internal_free"


def as_str(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def as_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    if isinstance(value, int):
        return datetime.fromtimestamp(value, UTC)
    return None


def extract_amount_cents(payload: Mapping[str, Any], *, candidates: tuple[str, ...]) -> int:
    for key in candidates:
        value = as_int(payload.get(key))
        if value is not None:
            return max(value, 0)
    return 0


def extract_event_fields(
    event: dict[str, Any],
    headers: Mapping[str, str],
) -> tuple[str, str, dict[str, Any]]:
    event_id = None
    for header_name in WEBHOOK_ID_HEADERS:
        event_id = as_str(headers.get(header_name))
        if event_id:
            break
    event_id = event_id or as_str(event.get("id"))
    event_type = as_str(event.get("type"))
    data = event.get("data")

    if not event_id or not event_type or not isinstance(data, dict):
        raise InvalidRequestError("Invalid Polar webhook payload.")

    return event_id, event_type, data


def is_definitive_duplicate_refund_error(detail: str) -> bool:
    normalized = detail.lower()
    duplicate_markers = (
        "already refunded",
        "already been refunded",
        "already has a refund",
        "refund already",
        "duplicate refund",
        "refund exists",
        "already exists",
    )
    return any(marker in normalized for marker in duplicate_markers)

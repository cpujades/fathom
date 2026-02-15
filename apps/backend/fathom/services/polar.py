from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fathom.core.config import Settings
from fathom.core.errors import ConfigurationError, ExternalServiceError, InvalidRequestError

WEBHOOK_TOLERANCE_SECONDS = 300


def get_polar_access_token(settings: Settings) -> str:
    if not settings.polar_access_token:
        raise ConfigurationError("POLAR_ACCESS_TOKEN is not configured.")
    return settings.polar_access_token


def get_polar_webhook_secret(settings: Settings) -> str:
    if not settings.polar_webhook_secret:
        raise ConfigurationError("POLAR_WEBHOOK_SECRET is not configured.")
    return settings.polar_webhook_secret


def get_polar_success_url(settings: Settings) -> str:
    if not settings.polar_success_url:
        raise ConfigurationError("POLAR_SUCCESS_URL is not configured.")
    return settings.polar_success_url


def get_polar_checkout_return_url(settings: Settings) -> str | None:
    return settings.polar_checkout_return_url


def get_polar_portal_return_url(settings: Settings) -> str:
    if not settings.polar_portal_return_url:
        raise ConfigurationError("POLAR_PORTAL_RETURN_URL is not configured.")
    return settings.polar_portal_return_url


def _get_api_base_url(settings: Settings) -> str:
    server = (settings.polar_server or "sandbox").strip().lower()

    if server == "sandbox":
        return "https://sandbox-api.polar.sh"
    if server == "production":
        return "https://api.polar.sh"
    if server.startswith("http://") or server.startswith("https://"):
        return server.rstrip("/")

    raise ConfigurationError("POLAR_SERVER must be 'sandbox', 'production', or an absolute HTTPS URL.")


def _extract_error_message(raw: str) -> str:
    if not raw:
        return "Unknown Polar API error."

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:300]

    if isinstance(payload, dict):
        for key in ("detail", "message", "error", "title"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return raw[:300]


def _polar_request(
    settings: Settings,
    *,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token = get_polar_access_token(settings)
    url = f"{_get_api_base_url(settings)}{path}"

    data: bytes | None = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = Request(url=url, method=method.upper(), data=data, headers=headers)

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="replace")
        message = _extract_error_message(raw_error)
        if 400 <= exc.code < 500:
            raise InvalidRequestError(f"Polar request failed: {message}") from exc
        raise ExternalServiceError(f"Polar request failed: {message}") from exc
    except URLError as exc:
        raise ExternalServiceError("Polar API is unreachable.") from exc

    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExternalServiceError("Polar returned a malformed JSON response.") from exc

    if not isinstance(parsed, dict):
        raise ExternalServiceError("Polar returned an unexpected response shape.")

    return parsed


async def create_checkout_session(
    settings: Settings,
    *,
    product_id: str,
    external_customer_id: str,
    metadata: dict[str, str],
) -> str:
    payload = {
        "products": [product_id],
        "success_url": get_polar_success_url(settings),
        "external_customer_id": external_customer_id,
        "metadata": metadata,
    }
    checkout_return_url = get_polar_checkout_return_url(settings)
    if checkout_return_url:
        payload["return_url"] = checkout_return_url

    response = await asyncio.to_thread(
        _polar_request,
        settings,
        method="POST",
        path="/v1/checkouts/",
        payload=payload,
    )
    checkout_url = response.get("url")
    if not isinstance(checkout_url, str) or not checkout_url:
        raise ExternalServiceError("Polar checkout URL was not returned.")

    return checkout_url


async def create_customer_portal_session(
    settings: Settings,
    *,
    external_customer_id: str,
) -> str:
    payload = {
        "external_customer_id": external_customer_id,
        "return_url": get_polar_portal_return_url(settings),
    }

    response = await asyncio.to_thread(
        _polar_request,
        settings,
        method="POST",
        path="/v1/customer-sessions/",
        payload=payload,
    )
    portal_url = response.get("customer_portal_url")
    if not isinstance(portal_url, str) or not portal_url:
        raise ExternalServiceError("Polar customer portal URL was not returned.")

    return portal_url


async def create_order_refund(
    settings: Settings,
    *,
    polar_order_id: str,
    amount_cents: int,
    reason: str = "customer_request",
) -> dict[str, Any]:
    payload = {
        "order_id": polar_order_id,
        "amount": amount_cents,
        "reason": reason,
    }

    return await asyncio.to_thread(
        _polar_request,
        settings,
        method="POST",
        path="/v1/refunds",
        payload=payload,
    )


def _decode_webhook_secret(secret: str) -> bytes:
    encoded = secret.strip()
    if encoded.startswith("whsec_"):
        encoded = encoded[len("whsec_") :]

    padded = encoded + ("=" * ((4 - (len(encoded) % 4)) % 4))
    try:
        return base64.urlsafe_b64decode(padded)
    except Exception as exc:  # noqa: BLE001
        raise InvalidRequestError("Invalid Polar webhook secret format.") from exc


def _parse_signatures(signature_header: str) -> list[bytes]:
    signatures: list[bytes] = []
    for token in signature_header.strip().split(" "):
        if not token:
            continue
        components = token.split(",", 1)
        if len(components) != 2:
            continue
        version, signature = components
        if version != "v1":
            continue
        try:
            signatures.append(base64.b64decode(signature))
        except Exception:  # noqa: BLE001
            continue
    return signatures


def verify_and_parse_webhook(
    payload: bytes,
    headers: Mapping[str, str],
    settings: Settings,
) -> dict[str, Any]:
    webhook_id = headers.get("webhook-id")
    webhook_timestamp = headers.get("webhook-timestamp")
    webhook_signature = headers.get("webhook-signature")

    if not webhook_id or not webhook_timestamp or not webhook_signature:
        raise InvalidRequestError("Missing required Polar webhook headers.")

    try:
        timestamp_seconds = int(webhook_timestamp)
    except ValueError as exc:
        raise InvalidRequestError("Invalid Polar webhook timestamp.") from exc

    now_seconds = int(datetime.now(UTC).timestamp())
    if abs(now_seconds - timestamp_seconds) > WEBHOOK_TOLERANCE_SECONDS:
        raise InvalidRequestError("Polar webhook timestamp is outside allowed tolerance.")

    secret = _decode_webhook_secret(get_polar_webhook_secret(settings))
    signed_content = f"{webhook_id}.{webhook_timestamp}.{payload.decode('utf-8')}".encode()
    expected_signature = hmac.new(secret, signed_content, hashlib.sha256).digest()

    signatures = _parse_signatures(webhook_signature)
    if not signatures:
        raise InvalidRequestError("Polar webhook signature header is invalid.")

    if not any(hmac.compare_digest(signature, expected_signature) for signature in signatures):
        raise InvalidRequestError("Polar webhook signature verification failed.")

    try:
        event = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidRequestError("Polar webhook payload is invalid JSON.") from exc

    if not isinstance(event, dict):
        raise InvalidRequestError("Polar webhook payload has an invalid shape.")

    return event

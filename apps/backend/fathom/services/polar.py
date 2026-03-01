from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from fathom.core.config import Settings
from fathom.core.errors import ConfigurationError, ExternalServiceError, InvalidRequestError

WEBHOOK_TOLERANCE_SECONDS = 300
WEBHOOK_SECRET_PREFIXES = ("whsec_", "polar_whs_", "polar_whsec_")
WEBHOOK_ID_HEADERS = ("webhook-id", "svix-id")
WEBHOOK_TIMESTAMP_HEADERS = ("webhook-timestamp", "svix-timestamp")
WEBHOOK_SIGNATURE_HEADERS = ("webhook-signature", "svix-signature")


class PolarInvalidRequestError(InvalidRequestError):
    """Polar returned a 4xx response with preserved HTTP status context."""

    def __init__(self, detail: str, *, http_status: int) -> None:
        super().__init__(detail)
        self.http_status = http_status


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
        "User-Agent": "Fathom-Backend/1.0",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    raw = ""
    current_url = url
    max_redirects = 2
    for _ in range(max_redirects + 1):
        request = Request(url=current_url, method=method.upper(), data=data, headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                break
        except HTTPError as exc:
            # Polar may redirect /v1/resource -> /v1/resource/ with 307/308.
            if exc.code in {307, 308}:
                location = exc.headers.get("Location")
                if location:
                    current_url = urljoin(current_url, location)
                    continue
                raise ExternalServiceError(f"Polar request redirect ({exc.code}) missing Location header.") from exc

            raw_error = exc.read().decode("utf-8", errors="replace")
            message = _extract_error_message(raw_error)
            if 400 <= exc.code < 500:
                raise PolarInvalidRequestError(
                    f"Polar request failed ({exc.code}): {message}",
                    http_status=exc.code,
                ) from exc
            raise ExternalServiceError(f"Polar request failed ({exc.code}): {message}") from exc
        except URLError as exc:
            raise ExternalServiceError("Polar API is unreachable.") from exc
    else:
        raise ExternalServiceError("Polar request failed due to redirect loop.")

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
        path="/v1/refunds/",
        payload=payload,
    )


def _candidate_webhook_secrets(secret: str) -> list[bytes]:
    raw_secret = secret.strip()
    if not raw_secret:
        raise InvalidRequestError("Invalid Polar webhook secret format.")

    encoded = raw_secret
    for prefix in WEBHOOK_SECRET_PREFIXES:
        if encoded.startswith(prefix):
            encoded = encoded[len(prefix) :]
            break

    candidates: list[bytes] = []
    seen: set[bytes] = set()

    for candidate in (raw_secret, encoded):
        raw_bytes = candidate.encode("utf-8")
        if raw_bytes and raw_bytes not in seen:
            candidates.append(raw_bytes)
            seen.add(raw_bytes)

        padded = candidate + ("=" * ((4 - (len(candidate) % 4)) % 4))
        for decoder in (base64.urlsafe_b64decode, base64.b64decode):
            try:
                decoded = decoder(padded)
            except Exception:  # noqa: BLE001
                continue
            if decoded and decoded not in seen:
                candidates.append(decoded)
                seen.add(decoded)

    if not candidates:
        raise InvalidRequestError("Invalid Polar webhook secret format.")
    return candidates


def _parse_signatures(signature_header: str) -> list[bytes]:
    signatures: list[bytes] = []
    matches = re.findall(r"(?:^|[\s,])v1[=,]([A-Za-z0-9+/=_-]+)", signature_header.strip())
    for signature in matches:
        padded = signature + ("=" * ((4 - (len(signature) % 4)) % 4))
        try:
            signatures.append(base64.urlsafe_b64decode(padded))
        except Exception:  # noqa: BLE001
            try:
                signatures.append(base64.b64decode(padded))
            except Exception:  # noqa: BLE001
                continue
    return signatures


def _get_header(headers: Mapping[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        value = headers.get(name)
        if value:
            return value
    return None


def verify_and_parse_webhook(
    payload: bytes,
    headers: Mapping[str, str],
    settings: Settings,
) -> dict[str, Any]:
    webhook_id = _get_header(headers, WEBHOOK_ID_HEADERS)
    webhook_timestamp = _get_header(headers, WEBHOOK_TIMESTAMP_HEADERS)
    webhook_signature = _get_header(headers, WEBHOOK_SIGNATURE_HEADERS)

    if not webhook_id or not webhook_timestamp or not webhook_signature:
        raise InvalidRequestError("Missing required Polar webhook headers.")

    try:
        timestamp_seconds = int(webhook_timestamp)
    except ValueError as exc:
        raise InvalidRequestError("Invalid Polar webhook timestamp.") from exc

    now_seconds = int(datetime.now(UTC).timestamp())
    if abs(now_seconds - timestamp_seconds) > WEBHOOK_TOLERANCE_SECONDS:
        raise InvalidRequestError("Polar webhook timestamp is outside allowed tolerance.")

    try:
        payload_str = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidRequestError("Polar webhook payload is not valid UTF-8.") from exc

    secrets = _candidate_webhook_secrets(get_polar_webhook_secret(settings))
    signed_content = f"{webhook_id}.{webhook_timestamp}.{payload_str}".encode()

    signatures = _parse_signatures(webhook_signature)
    if not signatures:
        raise InvalidRequestError("Polar webhook signature header is invalid.")

    expected_signatures = [hmac.new(secret, signed_content, hashlib.sha256).digest() for secret in secrets]
    is_valid_signature = any(
        hmac.compare_digest(signature, expected) for signature in signatures for expected in expected_signatures
    )
    if not is_valid_signature:
        raise InvalidRequestError("Polar webhook signature verification failed.")

    try:
        event = json.loads(payload_str)
    except json.JSONDecodeError as exc:
        raise InvalidRequestError("Polar webhook payload is invalid JSON.") from exc

    if not isinstance(event, dict):
        raise InvalidRequestError("Polar webhook payload has an invalid shape.")

    return event

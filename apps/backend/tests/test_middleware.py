from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

from fastapi import Request
from starlette.responses import PlainTextResponse

from fathom.core.errors import RateLimitError
from fathom.core.middleware import MAX_REQUEST_BYTES, log_requests
from fathom.core.rate_limits import _get_rate_limit_ip


def _request(*, client_host: str | None, forwarded_for: str | None = None) -> Request:
    headers: dict[str, str] = {}
    if forwarded_for is not None:
        headers["x-forwarded-for"] = forwarded_for

    client = SimpleNamespace(host=client_host) if client_host is not None else None
    return cast(Request, SimpleNamespace(headers=headers, client=client))


def _http_request(*, body: bytes = b"", rate_limit: int = 0) -> Request:
    delivered = False

    async def receive() -> dict[str, object]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    headers = [(b"content-length", str(len(body)).encode("ascii"))]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/briefing-sessions",
        "raw_path": b"/briefing-sessions",
        "query_string": b"",
        "headers": headers,
        "client": ("203.0.113.10", 1234),
        "server": ("api.example.com", 443),
        "app": SimpleNamespace(
            state=SimpleNamespace(
                rate_limit=rate_limit,
                strict_transport_security=True,
            )
        ),
    }
    return Request(scope, receive)


class RateLimitIpResolutionTests(unittest.TestCase):
    def test_ignores_forwarded_for_by_default(self) -> None:
        request = _request(client_host="10.0.0.5", forwarded_for="203.0.113.9")

        ip = _get_rate_limit_ip(request, trust_proxy_headers=False)

        self.assertEqual(ip, "10.0.0.5")

    def test_uses_forwarded_for_when_proxy_headers_are_trusted(self) -> None:
        request = _request(client_host="10.0.0.5", forwarded_for="203.0.113.9, 10.0.0.5")

        ip = _get_rate_limit_ip(
            request,
            trust_proxy_headers=True,
            trusted_proxy_networks=("10.0.0.0/8",),
        )

        self.assertEqual(ip, "203.0.113.9")

    def test_falls_back_to_client_host_when_forwarded_header_is_missing(self) -> None:
        request = _request(client_host="10.0.0.5")

        ip = _get_rate_limit_ip(
            request,
            trust_proxy_headers=True,
            trusted_proxy_networks=("10.0.0.0/8",),
        )

        self.assertEqual(ip, "10.0.0.5")

    def test_returns_unknown_when_no_client_information_exists(self) -> None:
        request = _request(client_host=None)

        ip = _get_rate_limit_ip(request, trust_proxy_headers=False)

        self.assertEqual(ip, "unknown")

    def test_ignores_spoofed_forwarded_header_from_untrusted_peer(self) -> None:
        request = _request(client_host="198.51.100.8", forwarded_for="203.0.113.9")

        ip = _get_rate_limit_ip(
            request,
            trust_proxy_headers=True,
            trusted_proxy_networks=("10.0.0.0/8",),
        )

        self.assertEqual(ip, "198.51.100.8")

    def test_ignores_invalid_forwarded_address_from_trusted_peer(self) -> None:
        request = _request(client_host="10.0.0.5", forwarded_for="not-an-ip")

        ip = _get_rate_limit_ip(
            request,
            trust_proxy_headers=True,
            trusted_proxy_networks=("10.0.0.0/8",),
        )

        self.assertEqual(ip, "10.0.0.5")


class RequestMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_oversized_request_returns_safe_413_response(self) -> None:
        request = _http_request(body=b"x" * (MAX_REQUEST_BYTES + 1))
        call_next = AsyncMock(return_value=PlainTextResponse("unreachable"))

        response = await log_requests(request, call_next)

        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            json.loads(response.body),
            {
                "error": {
                    "code": "request_too_large",
                    "message": "Request body too large.",
                }
            },
        )
        self.assertTrue(response.headers["x-request-id"])
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertIn("max-age=31536000", response.headers["strict-transport-security"])
        call_next.assert_not_awaited()

    async def test_rate_limit_error_returns_safe_429_response(self) -> None:
        request = _http_request(rate_limit=60)
        call_next = AsyncMock(return_value=PlainTextResponse("unreachable"))

        with patch(
            "fathom.core.middleware.maybe_enforce_rate_limit",
            AsyncMock(side_effect=RateLimitError("Too many requests.")),
        ):
            response = await log_requests(request, call_next)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(
            json.loads(response.body),
            {
                "error": {
                    "code": "rate_limit_exceeded",
                    "message": "Too many requests.",
                }
            },
        )
        self.assertTrue(response.headers["x-request-id"])
        self.assertEqual(
            response.headers["content-security-policy"],
            "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
        call_next.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

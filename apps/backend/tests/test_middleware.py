from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast

from fastapi import Request

from fathom.core.middleware import _get_rate_limit_ip


def _request(*, client_host: str | None, forwarded_for: str | None = None) -> Request:
    headers: dict[str, str] = {}
    if forwarded_for is not None:
        headers["x-forwarded-for"] = forwarded_for

    client = SimpleNamespace(host=client_host) if client_host is not None else None
    return cast(Request, SimpleNamespace(headers=headers, client=client))


class RateLimitIpResolutionTests(unittest.TestCase):
    def test_ignores_forwarded_for_by_default(self) -> None:
        request = _request(client_host="10.0.0.5", forwarded_for="203.0.113.9")

        ip = _get_rate_limit_ip(request, trust_proxy_headers=False)

        self.assertEqual(ip, "10.0.0.5")

    def test_uses_forwarded_for_when_proxy_headers_are_trusted(self) -> None:
        request = _request(client_host="10.0.0.5", forwarded_for="203.0.113.9, 10.0.0.5")

        ip = _get_rate_limit_ip(request, trust_proxy_headers=True)

        self.assertEqual(ip, "203.0.113.9")

    def test_falls_back_to_client_host_when_forwarded_header_is_missing(self) -> None:
        request = _request(client_host="10.0.0.5")

        ip = _get_rate_limit_ip(request, trust_proxy_headers=True)

        self.assertEqual(ip, "10.0.0.5")

    def test_returns_unknown_when_no_client_information_exists(self) -> None:
        request = _request(client_host=None)

        ip = _get_rate_limit_ip(request, trust_proxy_headers=False)

        self.assertEqual(ip, "unknown")


if __name__ == "__main__":
    unittest.main()

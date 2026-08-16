from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase

from starlette.requests import Request

from fathom.core.rate_limits import resolve_client_ip


def _request(*, peer: str, forwarded_for: str | None, trusted_proxy_networks: list[str]) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded_for:
        headers.append((b"x-forwarded-for", forwarded_for.encode("ascii")))

    app = SimpleNamespace(
        state=SimpleNamespace(
            trust_proxy_headers=bool(trusted_proxy_networks),
            trusted_proxy_networks=trusted_proxy_networks,
        )
    )
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/billing/checkout",
            "headers": headers,
            "client": (peer, 443),
            "app": app,
        }
    )


class CheckoutClientIpTests(TestCase):
    def test_uses_forwarded_customer_ip_from_a_trusted_proxy(self) -> None:
        request = _request(
            peer="10.0.0.5",
            forwarded_for="203.0.113.9, 10.0.0.5",
            trusted_proxy_networks=["10.0.0.0/8"],
        )

        self.assertEqual(resolve_client_ip(request), "203.0.113.9")

    def test_ignores_spoofed_forwarded_ip_from_an_untrusted_peer(self) -> None:
        request = _request(
            peer="198.51.100.8",
            forwarded_for="203.0.113.9",
            trusted_proxy_networks=["10.0.0.0/8"],
        )

        self.assertEqual(resolve_client_ip(request), "198.51.100.8")

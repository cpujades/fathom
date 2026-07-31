from __future__ import annotations

import io
import unittest
from email.message import Message
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch
from urllib.error import HTTPError

from fathom.core.config import Settings
from fathom.core.errors import ConfigurationError, ExternalServiceError
from fathom.services.polar import (
    MAX_POLAR_RESPONSE_BYTES,
    _get_api_base_url,
    _polar_request,
    _require_https_destination,
    get_order,
)


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, amount: int) -> bytes:
        return self.payload[:amount]


def _settings(*, server: str = "sandbox") -> Settings:
    return cast(
        Settings,
        SimpleNamespace(
            polar_access_token="test-token",
            polar_server=server,
        ),
    )


def _redirect(url: str, location: str) -> HTTPError:
    headers = Message()
    headers["Location"] = location
    return HTTPError(
        url,
        307,
        "Temporary Redirect",
        headers,
        io.BytesIO(b""),
    )


class PolarTransportTests(unittest.IsolatedAsyncioTestCase):
    def test_custom_api_base_requires_credential_free_https(self) -> None:
        self.assertEqual(
            _get_api_base_url(_settings(server="https://billing.example.test/polar/")),
            "https://billing.example.test/polar",
        )

        for server in (
            "http://billing.example.test",
            "https://user:password@billing.example.test",
            "https://billing.example.test?token=secret",
            "billing.example.test",
        ):
            with self.subTest(server=server), self.assertRaises(ConfigurationError):
                _get_api_base_url(_settings(server=server))

    def test_cross_origin_redirect_is_rejected_before_token_can_be_forwarded(self) -> None:
        redirect = _redirect(
            "https://sandbox-api.polar.sh/v1/orders/order-1",
            "https://attacker.example/collect",
        )

        with (
            patch(
                "fathom.services.polar._open_without_redirects",
                side_effect=redirect,
            ) as open_request,
            self.assertRaisesRegex(
                ExternalServiceError,
                "untrusted origin",
            ),
        ):
            _polar_request(
                _settings(),
                method="GET",
                path="/v1/orders/order-1",
            )

        open_request.assert_called_once()

    def test_relative_same_origin_redirect_preserves_expected_request(self) -> None:
        redirect = _redirect(
            "https://sandbox-api.polar.sh/v1/orders/order-1",
            "/v1/orders/order-1/",
        )

        with patch(
            "fathom.services.polar._open_without_redirects",
            side_effect=[redirect, _Response(b'{"id":"order-1"}')],
        ) as open_request:
            response = _polar_request(
                _settings(),
                method="GET",
                path="/v1/orders/order-1",
            )

        self.assertEqual(response, {"id": "order-1"})
        self.assertEqual(open_request.call_count, 2)
        redirected_request = cast(Any, open_request.call_args_list[1].args[0])
        self.assertEqual(
            redirected_request.full_url,
            "https://sandbox-api.polar.sh/v1/orders/order-1/",
        )
        self.assertEqual(
            redirected_request.get_header("Authorization"),
            "Bearer test-token",
        )

    def test_oversized_response_is_rejected_without_unbounded_read(self) -> None:
        with (
            patch(
                "fathom.services.polar._open_without_redirects",
                return_value=_Response(b"x" * (MAX_POLAR_RESPONSE_BYTES + 1)),
            ),
            self.assertRaisesRegex(ExternalServiceError, "oversized response"),
        ):
            _polar_request(
                _settings(),
                method="GET",
                path="/v1/orders/order-1",
            )

    def test_browser_destinations_must_be_https(self) -> None:
        self.assertEqual(
            _require_https_destination(
                "https://polar.sh/checkout/test",
                label="checkout",
            ),
            "https://polar.sh/checkout/test",
        )
        with self.assertRaisesRegex(ExternalServiceError, "invalid checkout"):
            _require_https_destination(
                "javascript:alert(1)",
                label="checkout",
            )

    async def test_provider_ids_are_encoded_as_single_path_segments(self) -> None:
        with patch(
            "fathom.services.polar._polar_request",
            return_value={"id": "order"},
        ) as polar_request:
            await get_order(
                _settings(),
                order_id="../subscriptions/private",
            )

        self.assertEqual(
            polar_request.call_args.kwargs["path"],
            "/v1/orders/..%2Fsubscriptions%2Fprivate",
        )


if __name__ == "__main__":
    unittest.main()

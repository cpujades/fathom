from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fathom.core.errors import ExternalServiceError
from fathom.crud.supabase.stream_leases import (
    claim_stream_lease,
    release_stream_lease,
    renew_stream_lease,
)


class StreamLeaseCrudTests(unittest.IsolatedAsyncioTestCase):
    async def test_claim_passes_bounded_lease_contract(self) -> None:
        execute = AsyncMock(return_value=SimpleNamespace(data="lease-token"))
        rpc_result = SimpleNamespace(execute=execute)
        client = SimpleNamespace(rpc=Mock(return_value=rpc_result))

        token = await claim_stream_lease(
            client,
            user_id="11111111-1111-1111-1111-111111111111",
            client_subject="ip:203.0.113.4",
            max_per_user=3,
            max_per_subject=12,
            lease_seconds=90,
        )

        self.assertEqual(token, "lease-token")
        client.rpc.assert_called_once_with(
            "claim_briefing_stream_lease",
            {
                "p_user_id": "11111111-1111-1111-1111-111111111111",
                "p_client_subject": "ip:203.0.113.4",
                "p_max_per_user": 3,
                "p_max_per_subject": 12,
                "p_lease_seconds": 90,
            },
        )

    async def test_claim_returns_none_when_capacity_is_exhausted(self) -> None:
        client = _rpc_client(None)

        self.assertIsNone(
            await claim_stream_lease(
                client,
                user_id="11111111-1111-1111-1111-111111111111",
                client_subject="ip:203.0.113.4",
                max_per_user=3,
                max_per_subject=12,
                lease_seconds=90,
            )
        )

    async def test_claim_rejects_unexpected_database_shape(self) -> None:
        client = _rpc_client({"lease_token": "unexpected"})

        with self.assertRaises(ExternalServiceError):
            await claim_stream_lease(
                client,
                user_id="11111111-1111-1111-1111-111111111111",
                client_subject="ip:203.0.113.4",
                max_per_user=3,
                max_per_subject=12,
                lease_seconds=90,
            )

    async def test_renew_and_release_require_database_confirmation(self) -> None:
        renewing_client = _rpc_client(True)
        releasing_client = _rpc_client(True)

        self.assertTrue(
            await renew_stream_lease(
                renewing_client,
                lease_token="lease-token",
                lease_seconds=90,
            )
        )
        await release_stream_lease(releasing_client, lease_token="lease-token")

    async def test_release_fails_closed_without_confirmation(self) -> None:
        with self.assertRaises(ExternalServiceError):
            await release_stream_lease(_rpc_client(False), lease_token="lease-token")


def _rpc_client(data: object) -> SimpleNamespace:
    return SimpleNamespace(
        rpc=Mock(
            return_value=SimpleNamespace(
                execute=AsyncMock(return_value=SimpleNamespace(data=data)),
            )
        )
    )


if __name__ == "__main__":
    unittest.main()

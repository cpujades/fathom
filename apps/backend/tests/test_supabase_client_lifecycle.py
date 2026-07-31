from __future__ import annotations

import asyncio
import gc
import unittest
import warnings

import httpx

from fathom.core.config import Settings
from fathom.services.supabase import (
    close_supabase_client,
    create_supabase_admin_client,
    create_supabase_user_client,
    managed_supabase_client,
)
from supabase import AsyncClient


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "OPENROUTER_API_KEY": "test-openrouter",
            "GROQ_API_KEY": "test-groq",
            "SUPABASE_URL": "http://127.0.0.1:54321",
            "SUPABASE_PUBLISHABLE_KEY": "test-publishable",
            "SUPABASE_SECRET_KEY": "test-secret",
        }
    )


class SupabaseClientLifecycleTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _transport(client: AsyncClient) -> httpx.AsyncClient:
        transport = client.options.httpx_client
        if not isinstance(transport, httpx.AsyncClient):
            raise AssertionError("Supabase client does not own an async HTTP transport")
        return transport

    async def test_user_clients_isolate_auth_and_close_only_their_transport(self) -> None:
        first = await create_supabase_user_client(_settings(), "first-token")
        second = await create_supabase_user_client(_settings(), "second-token")
        first_transport = self._transport(first)
        second_transport = self._transport(second)

        self.assertIsNot(first_transport, second_transport)
        self.assertEqual(first.options.headers["Authorization"], "Bearer first-token")
        self.assertEqual(second.options.headers["Authorization"], "Bearer second-token")

        await close_supabase_client(first)
        await close_supabase_client(first)

        self.assertTrue(first_transport.is_closed)
        self.assertFalse(second_transport.is_closed)
        await close_supabase_client(second)
        self.assertTrue(second_transport.is_closed)

    async def test_managed_client_closes_after_error(self) -> None:
        client = await create_supabase_admin_client(_settings())
        transport = self._transport(client)

        with self.assertRaisesRegex(RuntimeError, "boom"):
            async with managed_supabase_client(client):
                raise RuntimeError("boom")

        self.assertTrue(transport.is_closed)

    async def test_managed_client_closes_after_cancellation(self) -> None:
        client = await create_supabase_admin_client(_settings())
        transport = self._transport(client)
        entered = asyncio.Event()

        async def wait_forever() -> None:
            async with managed_supabase_client(client):
                entered.set()
                await asyncio.Future()

        task = asyncio.create_task(wait_forever())
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertTrue(transport.is_closed)

    async def test_closed_clients_emit_no_resource_warning(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            client = await create_supabase_admin_client(_settings())
            async with managed_supabase_client(client):
                self.assertFalse(self._transport(client).is_closed)
            del client
            gc.collect()

        resource_warnings = [
            str(warning.message) for warning in caught if issubclass(warning.category, ResourceWarning)
        ]
        self.assertEqual(resource_warnings, [])


if __name__ == "__main__":
    unittest.main()

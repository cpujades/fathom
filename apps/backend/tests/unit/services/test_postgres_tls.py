from __future__ import annotations

import asyncio
import unittest
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, patch

from fathom.core.config import Settings
from fathom.services.supabase.postgres import (
    _enqueue_job_event_signal,
    create_postgres_connection,
    create_postgres_pool,
    listen_for_job_event_notifications,
    listen_for_notifications,
)


def _settings(*, app_env: str) -> Settings:
    values: dict[str, object] = {
        "OPENROUTER_API_KEY": "test-openrouter",
        "GROQ_API_KEY": "test-groq",
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_PUBLISHABLE_KEY": "test-publishable",
        "SUPABASE_SECRET_KEY": "test-secret",
        "SUPABASE_DB_PASSWORD": "test-password",
        "SUPABASE_DB_HOST": "db.project.supabase.co",
        "APP_ENV": app_env,
    }
    if app_env in {"staging", "production"}:
        values.update(
            RATE_LIMIT=60,
            CORS_ALLOW_ORIGINS="https://app.talven.ai",
            POLAR_SERVER="production",
            POLAR_SUCCESS_URL="https://app.talven.ai/billing/success",
            POLAR_CHECKOUT_RETURN_URL="https://app.talven.ai/billing",
            POLAR_PORTAL_RETURN_URL="https://app.talven.ai/billing",
        )
    else:
        values.update(RATE_LIMIT=0, CORS_ALLOW_ORIGINS="")
    return Settings.model_validate(values)


class PostgresTlsTests(unittest.IsolatedAsyncioTestCase):
    async def test_job_event_queue_overflow_emits_reconciliation_signal(self) -> None:
        signal: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        first_job = "11111111-1111-4111-8111-111111111111"
        second_job = "22222222-2222-4222-8222-222222222222"

        _enqueue_job_event_signal(AsyncMock(), 1, "job_event_available", f'{{"job_id":"{first_job}"}}', signal=signal)
        _enqueue_job_event_signal(AsyncMock(), 1, "job_event_available", f'{{"job_id":"{second_job}"}}', signal=signal)

        self.assertEqual(await signal.get(), "overflow")

    async def test_strict_runtime_uses_certificate_verified_tls(self) -> None:
        connection = AsyncMock()
        with patch("fathom.services.supabase.postgres.asyncpg.connect", AsyncMock(return_value=connection)) as connect:
            async with create_postgres_connection(_settings(app_env="production")):
                pass

        self.assertTrue(connect.await_args.kwargs["ssl"])
        connection.close.assert_awaited_once()

    async def test_local_runtime_keeps_local_postgres_compatible(self) -> None:
        pool = AsyncMock()
        with patch(
            "fathom.services.supabase.postgres.asyncpg.create_pool",
            AsyncMock(return_value=pool),
        ) as create_pool:
            result = await create_postgres_pool(_settings(app_env="local"))

        self.assertIs(result, pool)
        self.assertFalse(create_pool.await_args.kwargs["ssl"])

    async def test_listener_reports_notifications_and_connection_termination(self) -> None:
        notification_callback: Any = None
        termination_callback: Any = None

        class FakeConnection:
            async def add_listener(self, _channel: str, callback: Any) -> None:
                nonlocal notification_callback
                notification_callback = callback

            async def remove_listener(self, _channel: str, _callback: Any) -> None:
                return None

            def add_termination_listener(self, callback: Any) -> None:
                nonlocal termination_callback
                termination_callback = callback

            def remove_termination_listener(self, _callback: Any) -> None:
                return None

            def is_closed(self) -> bool:
                return False

        connection = FakeConnection()

        @asynccontextmanager
        async def connected(_settings: Settings):
            yield connection

        with patch("fathom.services.supabase.postgres.create_postgres_connection", connected):
            async with listen_for_notifications(_settings(app_env="local"), "job_available") as signal:
                notification_callback(connection, 1, "job_available", "{}")
                self.assertEqual(await signal.get(), "notification")
                notification_callback(connection, 1, "job_available", '{"id":"job-2"}')
                termination_callback(connection)
                self.assertEqual(await signal.get(), "disconnected")

    async def test_job_event_listener_extracts_only_valid_job_ids(self) -> None:
        notification_callback: Any = None

        class FakeConnection:
            async def add_listener(self, _channel: str, callback: Any) -> None:
                nonlocal notification_callback
                notification_callback = callback

            async def remove_listener(self, _channel: str, _callback: Any) -> None:
                return None

            def add_termination_listener(self, _callback: Any) -> None:
                return None

            def remove_termination_listener(self, _callback: Any) -> None:
                return None

            def is_closed(self) -> bool:
                return False

        connection = FakeConnection()

        @asynccontextmanager
        async def connected(_settings: Settings):
            yield connection

        job_id = "11111111-1111-4111-8111-111111111111"
        with patch("fathom.services.supabase.postgres.create_postgres_connection", connected):
            async with listen_for_job_event_notifications(
                _settings(app_env="local"),
                "job_event_available",
            ) as signal:
                notification_callback(connection, 1, "job_event_available", '{"job_id":"invalid"}')
                self.assertTrue(signal.empty())
                notification_callback(
                    connection,
                    1,
                    "job_event_available",
                    f'{{"job_id":"{job_id}"}}',
                )
                self.assertEqual(await signal.get(), job_id)


if __name__ == "__main__":
    unittest.main()

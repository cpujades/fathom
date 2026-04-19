from __future__ import annotations

import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fathom.application.meta import readiness_status, status_snapshot
from fathom.core.errors import NotReadyError


def _settings(**overrides: object) -> SimpleNamespace:
    values = {
        "app_env": "production",
        "supabase_url": "https://example.supabase.co",
        "supabase_publishable_key": "sb_publishable",
        "supabase_secret_key": "sb_secret",
        "supabase_db_password": "secret",
        "supabase_db_user": "postgres",
        "supabase_db_name": "postgres",
        "supabase_db_host": "db.example.internal",
        "supabase_db_port": 5432,
        "polar_access_token": "polar_token",
        "polar_webhook_secret": "whsec_123",
        "polar_success_url": "https://app.example.com/billing/success",
        "polar_checkout_return_url": "https://app.example.com/app/billing",
        "polar_portal_return_url": "https://app.example.com/app/account",
        "polar_server": "production",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@asynccontextmanager
async def _postgres_ok(_settings: SimpleNamespace):
    connection = AsyncMock()
    connection.fetchval.return_value = 1
    yield connection


def _admin_client() -> MagicMock:
    client = MagicMock()
    execute = AsyncMock(return_value=None)
    client.table.return_value.select.return_value.limit.return_value.execute = execute
    return client


class ReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_readiness_passes_with_production_dependencies_ready(self) -> None:
        admin_client = _admin_client()

        with (
            patch("fathom.application.meta.create_supabase_admin_client", AsyncMock(return_value=admin_client)),
            patch("fathom.application.meta.create_postgres_connection", _postgres_ok),
        ):
            result = await readiness_status(_settings())

        self.assertEqual(result.status, "ok")

    async def test_readiness_fails_when_billing_is_not_configured(self) -> None:
        admin_client = _admin_client()

        with (
            patch("fathom.application.meta.create_supabase_admin_client", AsyncMock(return_value=admin_client)),
            patch("fathom.application.meta.create_postgres_connection", _postgres_ok),
        ):
            with self.assertRaises(NotReadyError) as ctx:
                await readiness_status(_settings(polar_access_token=None))

        self.assertIn("Billing is not configured", ctx.exception.detail)

    async def test_local_readiness_skips_billing_and_external_worker_checks(self) -> None:
        admin_client = _admin_client()

        with (
            patch("fathom.application.meta.create_supabase_admin_client", AsyncMock(return_value=admin_client)),
            patch("fathom.application.meta.create_postgres_connection", _postgres_ok),
        ):
            result = await readiness_status(
                _settings(
                    app_env="local",
                    polar_access_token=None,
                    polar_webhook_secret=None,
                    polar_success_url=None,
                    polar_portal_return_url=None,
                )
            )

        self.assertEqual(result.status, "ok")

    async def test_status_snapshot_returns_version_and_uptime(self) -> None:
        result = await status_snapshot()

        self.assertEqual(result.status, "ok")
        self.assertIsNotNone(result.version)
        self.assertIsNotNone(result.uptime_seconds)

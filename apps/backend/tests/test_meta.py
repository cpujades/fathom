from __future__ import annotations

import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fathom.api.routers.meta import router as meta_router
from fathom.application.meta import _REQUIRED_DATABASE_OBJECTS, readiness_status, status_snapshot
from fathom.core.errors import ConfigurationError, NotReadyError


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
    connection.fetchrow.return_value = {name: True for name in _REQUIRED_DATABASE_OBJECTS}
    yield connection


@asynccontextmanager
async def _postgres_with_missing_schema(_settings: SimpleNamespace):
    connection = AsyncMock()
    connection.fetchval.return_value = 1
    connection.fetchrow.return_value = {
        name: name != "prepare_summary_pdf_function" for name in _REQUIRED_DATABASE_OBJECTS
    }
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
        self.assertEqual(result.event_delivery, "degraded")
        selected_tables = [call.args[0] for call in admin_client.table.call_args_list]
        self.assertEqual(
            selected_tables,
            ["jobs", "summaries", "job_events", "transcript_segments"],
        )

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

    async def test_readiness_fails_when_required_schema_capability_is_missing(self) -> None:
        admin_client = _admin_client()

        with (
            patch("fathom.application.meta.create_supabase_admin_client", AsyncMock(return_value=admin_client)),
            patch("fathom.application.meta.create_postgres_connection", _postgres_with_missing_schema),
        ):
            with self.assertRaises(NotReadyError) as ctx:
                await readiness_status(_settings())

        self.assertEqual(ctx.exception.detail, "Database schema is incomplete.")

    async def test_readiness_converts_non_postgrest_api_failures_to_not_ready(self) -> None:
        with (
            patch(
                "fathom.application.meta.create_supabase_admin_client",
                AsyncMock(side_effect=OSError("network unavailable")),
            ),
            patch("fathom.application.meta.create_postgres_connection", _postgres_ok),
        ):
            with self.assertRaises(NotReadyError) as ctx:
                await readiness_status(_settings())

        self.assertEqual(ctx.exception.detail, "Supabase is not reachable.")

    async def test_readiness_does_not_expose_postgres_connection_details(self) -> None:
        @asynccontextmanager
        async def failed_postgres(_settings: SimpleNamespace):
            raise ConfigurationError("password for postgres@example.internal was rejected")
            yield  # pragma: no cover

        admin_client = _admin_client()
        with (
            patch("fathom.application.meta.create_supabase_admin_client", AsyncMock(return_value=admin_client)),
            patch("fathom.application.meta.create_postgres_connection", failed_postgres),
        ):
            with self.assertRaises(NotReadyError) as ctx:
                await readiness_status(_settings())

        self.assertEqual(ctx.exception.detail, "Direct Postgres is not configured.")

    async def test_public_status_endpoint_returns_only_coarse_event_delivery_state(self) -> None:
        coordinator = SimpleNamespace(
            status_snapshot=lambda: {
                "listener_healthy": True,
                "active_jobs": 2,
                "queued_jobs": 0,
                "inflight_jobs": 1,
                "notification_hints": 4,
                "notification_overflows": 0,
                "refresh_count": 3,
                "refresh_failures": 0,
                "fallback_reconciliations": 0,
            }
        )
        app = FastAPI()
        app.include_router(meta_router)
        app.state.job_event_coordinator = coordinator

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
            response = await client.get("/meta/status")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertIsNotNone(payload["version"])
        self.assertIsNotNone(payload["uptime_seconds"])
        self.assertEqual(payload["event_delivery"], "healthy")
        self.assertEqual(
            set(payload),
            {"status", "version", "uptime_seconds", "event_delivery"},
        )
        self.assertNotIn("active_jobs", str(payload))
        self.assertNotIn("notification_overflows", str(payload))

    async def test_status_snapshot_retains_detailed_event_metrics_in_structured_logs(self) -> None:
        event_delivery_metrics = {
            "listener_healthy": True,
            "active_jobs": 2,
            "queued_jobs": 0,
            "inflight_jobs": 1,
            "notification_hints": 4,
            "notification_overflows": 0,
            "refresh_count": 3,
            "refresh_failures": 0,
            "fallback_reconciliations": 0,
        }
        coordinator = SimpleNamespace(status_snapshot=lambda: event_delivery_metrics)

        with patch("fathom.application.meta.logger.info") as log_info:
            result = await status_snapshot(coordinator)

        self.assertEqual(result.event_delivery, "healthy")
        log_info.assert_called_once()
        self.assertEqual(log_info.call_args.args[0], "api.status.snapshot")
        self.assertEqual(
            log_info.call_args.kwargs["extra"]["event_delivery_metrics"],
            event_delivery_metrics,
        )

    async def test_listener_failure_degrades_but_does_not_fail_readiness(self) -> None:
        admin_client = _admin_client()
        coordinator = SimpleNamespace(status_snapshot=lambda: {"listener_healthy": False})

        with (
            patch("fathom.application.meta.create_supabase_admin_client", AsyncMock(return_value=admin_client)),
            patch("fathom.application.meta.create_postgres_connection", _postgres_ok),
        ):
            result = await readiness_status(_settings(), coordinator)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.event_delivery, "degraded")

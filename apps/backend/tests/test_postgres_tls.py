from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fathom.core.config import Settings
from fathom.services.supabase.postgres import create_postgres_connection, create_postgres_pool


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


if __name__ == "__main__":
    unittest.main()

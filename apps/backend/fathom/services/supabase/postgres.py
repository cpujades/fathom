"""Direct Postgres connection for LISTEN/NOTIFY support."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial
from typing import Any, cast
from urllib.parse import quote

import asyncpg

from fathom.core.config import Settings
from fathom.core.errors import ConfigurationError

logger = logging.getLogger(__name__)


def _build_postgres_url(settings: Settings) -> str | None:
    if not settings.supabase_db_password:
        return None

    host = settings.supabase_db_host
    user = settings.supabase_db_user
    name = settings.supabase_db_name
    port = settings.supabase_db_port
    password = quote(settings.supabase_db_password, safe="")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def _parse_notification_payload(payload: str) -> dict[str, Any] | None:
    try:
        import json

        data = json.loads(payload)
        if isinstance(data, dict):
            return cast(dict[str, Any], data)
        logger.error("notification payload is not an object")
        return None
    except Exception as exc:
        logger.error("failed to parse notification payload", exc_info=exc)
        return None


async def _enqueue_notification(
    _connection: asyncpg.Connection,
    _pid: int,
    _channel: str,
    payload: str,
    *,
    queue: asyncio.Queue[dict[str, Any]],
) -> None:
    data = _parse_notification_payload(payload)
    if data:
        await queue.put(data)


@asynccontextmanager
async def create_postgres_connection(settings: Settings) -> AsyncIterator[asyncpg.Connection]:
    """Create a direct Postgres connection for LISTEN/NOTIFY."""
    postgres_url = _build_postgres_url(settings)
    logger.info(f"postgres_url: {postgres_url}")
    if not postgres_url:
        raise ConfigurationError("SUPABASE_DB connection details are not configured.")

    try:
        conn = await asyncpg.connect(postgres_url, timeout=10)
        logger.info("postgres connection established")
        try:
            yield conn
        finally:
            await conn.close()
            logger.info("postgres connection closed")
    except Exception as exc:
        logger.error("failed to create postgres connection", exc_info=exc)
        raise ConfigurationError(f"Failed to connect to Postgres: {exc}") from exc


async def wait_for_job_created(
    settings: Settings,
    *,
    timeout_seconds: float = 10.0,
) -> dict[str, Any] | None:
    """Wait for a job_created notification.

    Returns the payload dict if a notification arrives before timeout, otherwise None.
    """
    async with create_postgres_connection(settings) as conn:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        notification_handler = partial(_enqueue_notification, queue=queue)
        await conn.add_listener("job_created", notification_handler)
        logger.info("listening to job_created channel")

        try:
            try:
                return await asyncio.wait_for(queue.get(), timeout=timeout_seconds)
            except TimeoutError:
                return None
        finally:
            await conn.remove_listener("job_created", notification_handler)
            logger.info("stopped listening to job_created channel")

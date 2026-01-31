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


async def _notification_handler(
    _connection: asyncpg.Connection,
    _pid: int,
    _channel: str,
    payload: str,
    *,
    job_id: str,
    queue: asyncio.Queue[dict[str, Any]],
) -> None:
    data = _parse_notification_payload(payload)
    if data and data.get("id") == job_id:
        await queue.put(data)


@asynccontextmanager
async def create_postgres_connection(settings: Settings) -> AsyncIterator[asyncpg.Connection]:
    """Create a direct Postgres connection for LISTEN/NOTIFY."""
    postgres_url = _build_postgres_url(settings)
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


async def listen_to_job_updates(
    settings: Settings,
    job_id: str,
    *,
    timeout_seconds: float = 30.0,
) -> AsyncIterator[dict[str, Any]]:
    """Listen to job update notifications from Postgres.

    Yields notification payloads when the job is updated.
    Raises asyncio.TimeoutError if no updates received within timeout.
    """
    async with create_postgres_connection(settings) as conn:
        # Create a queue to receive notifications
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        notification_handler = partial(_notification_handler, job_id=job_id, queue=queue)

        # Register listener
        await conn.add_listener("job_updates", notification_handler)
        logger.info(f"listening to job_updates channel for job {job_id}")

        try:
            while True:
                try:
                    # Wait for notification with timeout
                    notification = await asyncio.wait_for(
                        queue.get(),
                        timeout=timeout_seconds,
                    )
                    yield notification
                except TimeoutError:
                    # Send heartbeat and continue
                    logger.debug(f"no updates for job {job_id} in {timeout_seconds}s, continuing...")
                    # Yield empty dict to signal heartbeat
                    yield {}
        finally:
            await conn.remove_listener("job_updates", notification_handler)
            logger.info(f"stopped listening to job_updates channel for job {job_id}")

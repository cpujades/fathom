"""Direct Postgres connection for LISTEN/NOTIFY support."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg

from fathom.core.config import Settings
from fathom.core.errors import ConfigurationError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def create_postgres_connection(settings: Settings) -> AsyncIterator[asyncpg.Connection]:
    """Create a direct Postgres connection for LISTEN/NOTIFY."""
    postgres_url = settings.supabase_db_url
    if not postgres_url:
        raise ConfigurationError("SUPABASE_DB_URL is not configured.")

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

        async def notification_handler(
            connection: asyncpg.Connection,
            pid: int,
            channel: str,
            payload: str,
        ) -> None:
            """Handle incoming notifications."""
            try:
                import json

                data = json.loads(payload)
                # Filter notifications for this specific job
                if data.get("id") == job_id:
                    await queue.put(data)
            except Exception as exc:
                logger.error("failed to parse notification payload", exc_info=exc)

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

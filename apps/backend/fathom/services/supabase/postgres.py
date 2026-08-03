"""Direct Postgres connection for LISTEN/NOTIFY support."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal, cast
from urllib.parse import quote

import asyncpg

from fathom.core.config import Settings
from fathom.core.errors import ConfigurationError

logger = logging.getLogger(__name__)

PostgresNotificationSignal = Literal["notification", "disconnected"]


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
        logger.error("postgres.notification.invalid_payload")
        return None
    except Exception as exc:
        logger.error("postgres.notification.parse_failed", exc_info=exc)
        return None


def _enqueue_notification_signal(
    _connection: asyncpg.Connection,
    _pid: int,
    _channel: str,
    payload: str,
    *,
    signal: asyncio.Queue[PostgresNotificationSignal],
) -> None:
    data = _parse_notification_payload(payload)
    if data is not None and not signal.full():
        signal.put_nowait("notification")


def _enqueue_disconnect_signal(
    _connection: asyncpg.Connection,
    *,
    signal: asyncio.Queue[PostgresNotificationSignal],
) -> None:
    # A disconnect must win over a queued notification so the supervisor does
    # not wait forever on a dead LISTEN connection.
    if signal.full():
        signal.get_nowait()
    signal.put_nowait("disconnected")


@asynccontextmanager
async def create_postgres_connection(settings: Settings) -> AsyncIterator[asyncpg.Connection]:
    """Create a direct Postgres connection for LISTEN/NOTIFY."""
    postgres_url = _build_postgres_url(settings)
    if not postgres_url:
        raise ConfigurationError("SUPABASE_DB connection details are not configured.")

    try:
        conn = await asyncpg.connect(
            postgres_url,
            timeout=10,
            ssl=True if settings.is_strict_runtime else False,
        )
        logger.debug("postgres.connection.established")
        try:
            yield conn
        finally:
            await conn.close()
            logger.debug("postgres.connection.closed")
    except Exception as exc:
        logger.error("postgres.connection.failed", exc_info=exc)
        raise ConfigurationError("Failed to connect to Postgres.") from exc


async def create_postgres_pool(settings: Settings) -> asyncpg.Pool:
    postgres_url = _build_postgres_url(settings)
    if not postgres_url:
        raise ConfigurationError("SUPABASE_DB connection details are not configured.")

    try:
        pool = await asyncpg.create_pool(
            postgres_url,
            timeout=10,
            ssl=True if settings.is_strict_runtime else False,
            min_size=1,
            max_size=10,
        )
        logger.debug("postgres.pool.established")
        return pool
    except Exception as exc:
        logger.error("postgres.pool.failed", exc_info=exc)
        raise ConfigurationError("Failed to create Postgres pool.") from exc


@asynccontextmanager
async def listen_for_notifications(
    settings: Settings,
    channel: str,
) -> AsyncIterator[asyncio.Queue[PostgresNotificationSignal]]:
    async with create_postgres_connection(settings) as conn:
        # The payload is only a wake-up hint; durable job data stays in Postgres.
        # A one-slot queue coalesces bursts without growing memory or losing the
        # final wake-up to an Event.clear() race.
        signal: asyncio.Queue[PostgresNotificationSignal] = asyncio.Queue(maxsize=1)

        def notification_handler(
            connection: asyncpg.Connection,
            pid: int,
            notification_channel: str,
            payload: str,
        ) -> None:
            _enqueue_notification_signal(
                connection,
                pid,
                notification_channel,
                payload,
                signal=signal,
            )

        def termination_handler(connection: asyncpg.Connection) -> None:
            _enqueue_disconnect_signal(connection, signal=signal)

        await conn.add_listener(channel, notification_handler)
        conn.add_termination_listener(termination_handler)
        logger.info("postgres.listen.started", extra={"channel": channel})
        try:
            yield signal
        finally:
            conn.remove_termination_listener(termination_handler)
            if not conn.is_closed():
                await conn.remove_listener(channel, notification_handler)
            logger.info("postgres.listen.stopped", extra={"channel": channel})

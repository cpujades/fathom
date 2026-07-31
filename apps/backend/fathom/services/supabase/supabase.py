"""Supabase client factories."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx

from fathom.core.config import Settings
from fathom.core.errors import ConfigurationError
from supabase import AsyncClient, AsyncClientOptions, create_async_client

_OWNED_HTTP_CLIENT_ATTRIBUTE = "_fathom_owned_http_client"
SUPABASE_HTTP_TIMEOUT_SECONDS = 120.0


def _normalize_supabase_url(url: str) -> str:
    """Ensure the Supabase URL has a trailing slash (required by storage client)."""
    return url.rstrip("/") + "/"


async def create_supabase_admin_client(settings: Settings) -> AsyncClient:
    """Create an admin client with one explicitly owned HTTP transport."""
    missing: list[str] = []
    if not settings.supabase_url:
        missing.append("SUPABASE_URL")
    if not settings.supabase_secret_key:
        missing.append("SUPABASE_SECRET_KEY")
    if missing:
        missing_str = ", ".join(missing)
        raise ConfigurationError(f"Supabase admin client is not configured. Missing {missing_str}.")

    supabase_url = _normalize_supabase_url(settings.supabase_url)
    return await _create_owned_client(
        supabase_url,
        settings.supabase_secret_key,
        headers={},
    )


async def create_supabase_user_client(settings: Settings, access_token: str) -> AsyncClient:
    """Create a user-scoped client with an isolated Authorization header."""
    missing: list[str] = []
    if not settings.supabase_url:
        missing.append("SUPABASE_URL")
    if not settings.supabase_publishable_key:
        missing.append("SUPABASE_PUBLISHABLE_KEY")
    if missing:
        missing_str = ", ".join(missing)
        raise ConfigurationError(f"Supabase user client is not configured. Missing {missing_str}.")

    supabase_url = _normalize_supabase_url(settings.supabase_url)
    return await _create_owned_client(
        supabase_url,
        settings.supabase_publishable_key,
        headers={
            "Authorization": f"Bearer {access_token}",
        },
    )


async def _create_owned_client(
    supabase_url: str,
    supabase_key: str,
    *,
    headers: dict[str, str],
) -> AsyncClient:
    http_client = httpx.AsyncClient(timeout=SUPABASE_HTTP_TIMEOUT_SECONDS)
    options = AsyncClientOptions(
        headers=headers,
        persist_session=False,
        httpx_client=http_client,
    )
    try:
        client = await create_async_client(supabase_url, supabase_key, options)
    except BaseException:
        await http_client.aclose()
        raise
    setattr(client, _OWNED_HTTP_CLIENT_ATTRIBUTE, http_client)
    return client


async def close_supabase_client(client: Any) -> None:
    """Close the transport owned by a Fathom-created Supabase client once."""
    http_client = getattr(client, _OWNED_HTTP_CLIENT_ATTRIBUTE, None)
    if not isinstance(http_client, httpx.AsyncClient):
        return
    setattr(client, _OWNED_HTTP_CLIENT_ATTRIBUTE, None)
    await http_client.aclose()


@asynccontextmanager
async def managed_supabase_client(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    """Close a Fathom-created client after success, failure, or cancellation."""
    try:
        yield client
    finally:
        await close_supabase_client(client)

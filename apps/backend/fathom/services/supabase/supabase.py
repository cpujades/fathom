"""Supabase client factories."""

from __future__ import annotations

from fathom.core.config import Settings
from fathom.core.errors import ConfigurationError
from supabase import AsyncClient, AsyncClientOptions, create_async_client


def _normalize_supabase_url(url: str) -> str:
    """Ensure the Supabase URL has a trailing slash (required by storage client)."""
    return url.rstrip("/") + "/"


async def create_supabase_admin_client(settings: Settings) -> AsyncClient:
    """Create a Supabase client with admin (service role) credentials."""
    missing: list[str] = []
    if not settings.supabase_url:
        missing.append("SUPABASE_URL")
    if not settings.supabase_secret_key:
        missing.append("SUPABASE_SECRET_KEY")
    if missing:
        missing_str = ", ".join(missing)
        raise ConfigurationError(f"Supabase admin client is not configured. Missing {missing_str}.")

    supabase_url = _normalize_supabase_url(settings.supabase_url)
    return await create_async_client(supabase_url, settings.supabase_secret_key)


async def create_supabase_user_client(settings: Settings, access_token: str) -> AsyncClient:
    """Create a Supabase client scoped to a user's JWT for RLS."""
    missing: list[str] = []
    if not settings.supabase_url:
        missing.append("SUPABASE_URL")
    if not settings.supabase_publishable_key:
        missing.append("SUPABASE_PUBLISHABLE_KEY")
    if missing:
        missing_str = ", ".join(missing)
        raise ConfigurationError(f"Supabase user client is not configured. Missing {missing_str}.")

    options = AsyncClientOptions(
        headers={
            "Authorization": f"Bearer {access_token}",
        },
        persist_session=False,
    )
    supabase_url = _normalize_supabase_url(settings.supabase_url)
    return await create_async_client(supabase_url, settings.supabase_publishable_key, options)

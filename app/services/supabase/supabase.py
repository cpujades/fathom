"""Supabase client factories."""

from __future__ import annotations

from app.core.config import Settings
from app.core.errors import ConfigurationError
from supabase import AsyncClient, AsyncClientOptions, create_async_client


async def create_supabase_admin_client(settings: Settings) -> AsyncClient:
    """Create a Supabase client with admin (service role) credentials."""
    if not settings.supabase_url or not settings.supabase_secret_key:
        raise ConfigurationError("Supabase admin client is not configured.")

    return await create_async_client(settings.supabase_url, settings.supabase_secret_key)


async def create_supabase_user_client(settings: Settings, access_token: str) -> AsyncClient:
    """Create a Supabase client scoped to a user's JWT for RLS."""
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise ConfigurationError("Supabase user client is not configured.")

    options = AsyncClientOptions(
        headers={
            "Authorization": f"Bearer {access_token}",
            "apikey": settings.supabase_publishable_key,
        }
    )
    return await create_async_client(settings.supabase_url, settings.supabase_publishable_key, options)

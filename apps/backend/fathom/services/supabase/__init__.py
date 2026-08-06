"""Supabase service utilities."""

from fathom.services.supabase.helpers import (
    first_row,
    is_unique_violation,
    raise_for_auth_error,
    raise_for_postgrest_error,
    raise_for_storage_error,
)
from fathom.services.supabase.postgres import (
    create_postgres_connection,
    create_postgres_pool,
    listen_for_job_event_notifications,
    listen_for_notifications,
)
from fathom.services.supabase.supabase import (
    close_supabase_client,
    create_supabase_admin_client,
    create_supabase_user_client,
    managed_supabase_client,
)

__all__ = [
    "close_supabase_client",
    "create_supabase_admin_client",
    "create_supabase_user_client",
    "managed_supabase_client",
    "create_postgres_connection",
    "create_postgres_pool",
    "listen_for_job_event_notifications",
    "listen_for_notifications",
    "first_row",
    "is_unique_violation",
    "raise_for_auth_error",
    "raise_for_postgrest_error",
    "raise_for_storage_error",
]

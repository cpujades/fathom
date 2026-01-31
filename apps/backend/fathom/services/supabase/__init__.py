"""Supabase service utilities."""

from fathom.services.supabase.helpers import (
    first_row,
    is_unique_violation,
    raise_for_auth_error,
    raise_for_postgrest_error,
    raise_for_storage_error,
)
from fathom.services.supabase.postgres import create_postgres_connection, wait_for_job_created
from fathom.services.supabase.supabase import create_supabase_admin_client, create_supabase_user_client

__all__ = [
    "create_supabase_admin_client",
    "create_supabase_user_client",
    "create_postgres_connection",
    "wait_for_job_created",
    "first_row",
    "is_unique_violation",
    "raise_for_auth_error",
    "raise_for_postgrest_error",
    "raise_for_storage_error",
]

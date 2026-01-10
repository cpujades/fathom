"""Supabase client and data operations."""

from __future__ import annotations

from typing import Any

from postgrest import APIError
from storage3.exceptions import StorageApiError

from app.core.config import Settings
from app.core.errors import ConfigurationError, ExternalServiceError
from app.services.supabase_helpers import (
    first_row,
    raise_for_postgrest_error,
    raise_for_storage_error,
)
from supabase import Client, ClientOptions, create_client

# ---------------------------------------------------------------------------
# Client factories
# ---------------------------------------------------------------------------


def create_supabase_admin_client(settings: Settings) -> Client:
    """Create a Supabase client with admin (service role) credentials."""
    if not settings.supabase_url or not settings.supabase_secret_key:
        raise ConfigurationError("Supabase admin client is not configured.")

    return create_client(settings.supabase_url, settings.supabase_secret_key)


def create_supabase_user_client(settings: Settings, access_token: str) -> Client:
    """Create a Supabase client scoped to a user's JWT for RLS."""
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise ConfigurationError("Supabase user client is not configured.")

    options = ClientOptions(
        headers={
            "Authorization": f"Bearer {access_token}",
            "apikey": settings.supabase_publishable_key,
        }
    )
    return create_client(settings.supabase_url, settings.supabase_publishable_key, options)


# ---------------------------------------------------------------------------
# Job operations
# ---------------------------------------------------------------------------


def create_job(client: Client, *, url: str, user_id: str) -> dict[str, Any]:
    """Insert a new job row and return it."""
    try:
        response = client.table("jobs").insert({"url": url, "user_id": user_id}).execute()
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to create job.")

    return first_row(response.data, error_message="Failed to create job.")


def fetch_job(client: Client, job_id: str) -> dict[str, Any]:
    """Fetch a job by ID."""
    try:
        response = (
            client.table("jobs")
            .select("id,status,summary_id,error_code,error_message")
            .eq("id", job_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch job.")

    return first_row(
        response.data,
        error_message="Supabase returned an unexpected jobs shape.",
        not_found_message="Job not found.",
    )


# ---------------------------------------------------------------------------
# Summary operations
# ---------------------------------------------------------------------------


def fetch_summary(client: Client, summary_id: str) -> dict[str, Any]:
    """Fetch a summary by ID."""
    try:
        response = (
            client.table("summaries")
            .select("id,summary_markdown,pdf_object_key")
            .eq("id", summary_id)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        raise_for_postgrest_error(exc, "Failed to fetch summary.")

    return first_row(
        response.data,
        error_message="Supabase returned an unexpected summaries shape.",
        not_found_message="Summary not found.",
    )


# ---------------------------------------------------------------------------
# Storage operations
# ---------------------------------------------------------------------------


def create_pdf_signed_url(
    client: Client,
    bucket: str,
    object_key: str | None,
    ttl_seconds: int,
) -> str | None:
    """Generate a signed URL for a PDF in storage."""
    if not object_key:
        return None

    if not bucket:
        raise ConfigurationError("Supabase bucket is not configured.")

    try:
        response = client.storage.from_(bucket).create_signed_url(object_key, ttl_seconds)
    except StorageApiError as exc:
        raise_for_storage_error(exc, "Failed to sign PDF URL.")

    signed_url = response.get("signedURL") or response.get("signed_url")
    if not isinstance(signed_url, str) or not signed_url:
        raise ExternalServiceError("Signed PDF URL was not returned.")

    return signed_url


def upload_pdf(
    client: Client,
    *,
    bucket: str,
    object_key: str,
    pdf_bytes: bytes,
) -> None:
    """Upload a PDF to storage."""
    if not bucket:
        raise ConfigurationError("Supabase bucket is not configured.")
    if not object_key:
        raise ExternalServiceError("PDF object key is missing.")

    try:
        client.storage.from_(bucket).upload(
            object_key,
            pdf_bytes,
            {"content-type": "application/pdf", "upsert": "true"},
        )
    except StorageApiError as exc:
        raise_for_storage_error(exc, "Failed to upload PDF.")

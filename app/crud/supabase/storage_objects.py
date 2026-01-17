"""Supabase storage object helpers."""

from __future__ import annotations

from storage3.exceptions import StorageApiError

from app.core.errors import ConfigurationError, ExternalServiceError
from app.services.supabase.helpers import raise_for_storage_error
from supabase import AsyncClient


async def create_pdf_signed_url(
    client: AsyncClient,
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
        response = await client.storage.from_(bucket).create_signed_url(object_key, ttl_seconds)
    except StorageApiError as exc:
        raise_for_storage_error(exc, "Failed to sign PDF URL.")

    signed_url = response.get("signedURL") or response.get("signed_url")
    if not isinstance(signed_url, str) or not signed_url:
        raise ExternalServiceError("Signed PDF URL was not returned.")

    return signed_url


async def upload_pdf(
    client: AsyncClient,
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
        await client.storage.from_(bucket).upload(
            object_key,
            pdf_bytes,
            {"content-type": "application/pdf", "upsert": "true"},
        )
    except StorageApiError as exc:
        raise_for_storage_error(exc, "Failed to upload PDF.")

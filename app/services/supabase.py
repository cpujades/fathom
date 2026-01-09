from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from app.core.config import Settings
from app.core.errors import ConfigurationError, ExternalServiceError, NotFoundError
from supabase import Client, ClientOptions, create_client


def _first_row(value: Any, *, empty_message: str) -> dict[str, Any]:
    """
    Supabase client response typing is broad (JSON unions). We validate at runtime
    and narrow for type-checkers.
    """

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ExternalServiceError(empty_message)
    if not value:
        raise ExternalServiceError(empty_message)

    row = value[0]
    if not isinstance(row, Mapping):
        raise ExternalServiceError(empty_message)

    return cast(dict[str, Any], dict(row))


def create_supabase_admin_client(settings: Settings) -> Client:
    if not settings.supabase_url or not settings.supabase_secret_key:
        raise ConfigurationError("Supabase admin client is not configured.")

    return create_client(settings.supabase_url, settings.supabase_secret_key)


def create_supabase_user_client(settings: Settings, access_token: str) -> Client:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise ConfigurationError("Supabase user client is not configured.")

    options = ClientOptions(
        headers={
            # Supabase expects a user JWT to apply RLS.
            "Authorization": f"Bearer {access_token}",
            # Defense-in-depth: ensure apikey stays present even if defaults change.
            "apikey": settings.supabase_publishable_key,
        }
    )
    return create_client(settings.supabase_url, settings.supabase_publishable_key, options)


def create_job(client: Client, *, url: str, user_id: str) -> dict[str, Any]:
    try:
        response = client.table("jobs").insert({"url": url, "user_id": user_id}).execute()
    except Exception as exc:
        raise ExternalServiceError("Failed to create job.") from exc

    return _first_row(response.data, empty_message="Failed to create job.")


def fetch_job(client: Client, job_id: str) -> dict[str, Any]:
    try:
        response = (
            client.table("jobs")
            .select("id,status,summary_id,error_code,error_message")
            .eq("id", job_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise ExternalServiceError("Failed to fetch job.") from exc

    try:
        return _first_row(response.data, empty_message="Job not found.")
    except ExternalServiceError as exc:
        raise NotFoundError("Job not found.") from exc


def fetch_summary(client: Client, summary_id: str) -> dict[str, Any]:
    try:
        response = (
            client.table("summaries")
            .select("id,summary_markdown,pdf_object_key")
            .eq("id", summary_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise ExternalServiceError("Failed to fetch summary.") from exc

    try:
        return _first_row(response.data, empty_message="Summary not found.")
    except ExternalServiceError as exc:
        raise NotFoundError("Summary not found.") from exc


def create_pdf_signed_url(
    client: Client,
    bucket: str,
    object_key: str | None,
    ttl_seconds: int,
) -> str | None:
    if not object_key:
        return None

    if not bucket:
        raise ConfigurationError("Supabase bucket is not configured.")

    try:
        response = client.storage.from_(bucket).create_signed_url(object_key, ttl_seconds)
    except Exception as exc:
        raise ExternalServiceError("Failed to sign PDF URL.") from exc

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
    except Exception as exc:
        raise ExternalServiceError("Failed to upload PDF.") from exc

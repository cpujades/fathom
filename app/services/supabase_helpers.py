"""Helpers for Supabase error handling and response parsing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, NoReturn

from postgrest import APIError
from storage3.exceptions import StorageApiError
from supabase_auth.errors import AuthApiError

from app.core.errors import (
    AuthenticationError,
    ExternalServiceError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
)

# ---------------------------------------------------------------------------
# Auth error codes
# https://supabase.com/docs/guides/auth/debugging/error-codes
# ---------------------------------------------------------------------------
AUTH_RATE_LIMIT_CODES = frozenset(
    {
        "over_request_rate_limit",
        "over_email_send_rate_limit",
        "over_sms_send_rate_limit",
    }
)
AUTH_FORBIDDEN_CODES = frozenset({"user_banned"})

# ---------------------------------------------------------------------------
# Storage error codes
# https://supabase.com/docs/guides/storage/debugging/error-codes
# ---------------------------------------------------------------------------
STORAGE_AUTH_CODES = frozenset({"InvalidJWT"})
STORAGE_FORBIDDEN_CODES = frozenset({"AccessDenied"})
STORAGE_NOT_FOUND_CODES = frozenset({"NoSuchBucket", "NoSuchKey", "NoSuchUpload"})
STORAGE_RATE_LIMIT_CODES = frozenset({"SlowDown"})

# ---------------------------------------------------------------------------
# PostgREST error codes
# https://docs.postgrest.org/en/v12/references/errors.html
# ---------------------------------------------------------------------------
# Group 3 - JWT errors (authentication failures, not authorization)
POSTGREST_AUTH_CODES = frozenset({"PGRST301", "PGRST302"})
# RLS failures: 42501 = insufficient_privilege (PostgreSQL)
POSTGREST_FORBIDDEN_CODES = frozenset({"42501"})


def raise_for_auth_error(exc: AuthApiError, fallback_message: str) -> NoReturn:
    """Convert AuthApiError to the appropriate AppError subclass and raise."""
    code = getattr(exc, "code", None) or ""

    if code in AUTH_RATE_LIMIT_CODES:
        raise RateLimitError("Auth rate limit exceeded.") from exc
    if code in AUTH_FORBIDDEN_CODES:
        raise ForbiddenError("User access is forbidden.") from exc

    # Default: treat as authentication failure (invalid/expired token, etc.)
    raise AuthenticationError(fallback_message) from exc


def raise_for_storage_error(exc: StorageApiError, fallback_message: str) -> NoReturn:
    """Convert StorageApiError to the appropriate AppError subclass and raise."""
    code = getattr(exc, "code", None) or ""

    if code in STORAGE_AUTH_CODES:
        raise AuthenticationError("Storage authentication failed.") from exc
    if code in STORAGE_FORBIDDEN_CODES:
        raise ForbiddenError("Access denied to storage resource.") from exc
    if code in STORAGE_NOT_FOUND_CODES:
        raise NotFoundError("Storage resource not found.") from exc
    if code in STORAGE_RATE_LIMIT_CODES:
        raise RateLimitError("Storage rate limit exceeded.") from exc

    raise ExternalServiceError(fallback_message) from exc


def raise_for_postgrest_error(exc: APIError, fallback_message: str) -> NoReturn:
    """Convert PostgREST APIError to the appropriate AppError subclass and raise."""
    code = getattr(exc, "code", None) or ""

    if code in POSTGREST_AUTH_CODES:
        raise AuthenticationError("Database authentication failed.") from exc
    if code in POSTGREST_FORBIDDEN_CODES:
        raise ForbiddenError("Access denied to database resource.") from exc

    raise ExternalServiceError(fallback_message) from exc


def first_row(
    value: Any,
    *,
    error_message: str,
    not_found_message: str | None = None,
) -> dict[str, Any]:
    """
    Extract the first row from a Supabase response.

    Raises:
        ExternalServiceError: If the response structure is malformed.
        NotFoundError: If the result is empty and not_found_message is provided.
    """
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ExternalServiceError(error_message)

    if not value:
        if not_found_message is not None:
            raise NotFoundError(not_found_message)
        raise ExternalServiceError(error_message)

    row = value[0]
    if not isinstance(row, Mapping):
        raise ExternalServiceError(error_message)

    return dict(row)

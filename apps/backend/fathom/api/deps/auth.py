from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError
from jwt import decode as jwt_decode
from supabase_auth.errors import AuthApiError

from fathom.core.config import Settings, get_settings
from fathom.core.errors import AppError, AuthenticationError, ConfigurationError, ExternalServiceError
from fathom.core.logging import log_context
from fathom.services.supabase import create_supabase_user_client
from fathom.services.supabase.helpers import raise_for_auth_error

security = HTTPBearer(auto_error=False)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthContext:
    access_token: str
    user_id: str


def _extract_user_id(user: Any) -> str | None:
    """
    Extract user ID from Supabase auth response.

    Supabase SDK returns either a User object directly or a UserResponse wrapper
    depending on the SDK version and method used. This handles both cases.
    """
    if hasattr(user, "id") and user.id:
        return str(user.id)
    if hasattr(user, "user") and hasattr(user.user, "id") and user.user.id:
        return str(user.user.id)
    return None


def _decode_local_jwt(access_token: str, settings: Settings) -> AuthContext:
    if not settings.supabase_jwt_secret:
        raise ConfigurationError("SUPABASE_JWT_SECRET is required when SUPABASE_AUTH_MODE=local.")

    options = {"verify_aud": bool(settings.supabase_jwt_audience)}
    decode_kwargs: dict[str, Any] = {
        "key": settings.supabase_jwt_secret,
        "algorithms": ["HS256"],
        "options": options,
    }
    if settings.supabase_jwt_audience:
        decode_kwargs["audience"] = settings.supabase_jwt_audience
    try:
        claims = jwt_decode(access_token, **decode_kwargs)
    except ExpiredSignatureError as exc:
        raise AuthenticationError("Auth token expired.") from exc
    except InvalidTokenError as exc:
        raise AuthenticationError("Invalid auth token.") from exc

    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise AuthenticationError("Invalid auth token.")

    return AuthContext(access_token=access_token, user_id=str(user_id))


async def get_auth_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthContext:
    request_id = getattr(request.state, "request_id", None)
    base_log_context = {
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
    }
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        with log_context(**base_log_context):
            logger.warning("Missing or invalid Authorization header.", extra={"error_code": "unauthorized"})
        raise AuthenticationError("Missing or invalid Authorization header.")

    access_token = credentials.credentials
    auth_mode = (settings.supabase_auth_mode or "remote").lower()

    try:
        if auth_mode == "local":
            return _decode_local_jwt(access_token, settings)
        supabase = await create_supabase_user_client(settings, access_token)
        user = await supabase.auth.get_user(jwt=access_token)
    except AuthApiError as exc:
        auth_code = getattr(exc, "code", "") or "unknown"
        auth_status = getattr(exc, "status", None)
        with log_context(**base_log_context):
            logger.warning(
                "Supabase auth.get_user failed.",
                extra={
                    "error_code": "unauthorized",
                    "auth_error_code": auth_code,
                    "auth_status": auth_status,
                },
            )
        raise_for_auth_error(exc, "Invalid or expired auth token.")
    except AppError:
        # Let app errors (ConfigurationError, etc.) bubble up with correct status codes.
        raise
    except Exception as exc:
        # Unexpected errors (network issues, timeouts, etc.)
        with log_context(**base_log_context):
            logger.exception(
                "Unexpected error while validating auth token.",
                extra={"error_code": "external_service_error"},
            )
        raise ExternalServiceError("Failed to validate auth token.") from exc

    user_id = _extract_user_id(user)
    if not user_id:
        with log_context(**base_log_context):
            logger.warning(
                "Supabase returned no user id for token.",
                extra={"error_code": "unauthorized"},
            )
        raise AuthenticationError("Invalid auth token.")

    return AuthContext(access_token=access_token, user_id=user_id)

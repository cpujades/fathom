from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase_auth.errors import AuthApiError

from app.core.config import Settings, get_settings
from app.core.errors import AppError, AuthenticationError, ExternalServiceError
from app.services.supabase import create_supabase_user_client
from app.services.supabase.helpers import raise_for_auth_error

security = HTTPBearer(auto_error=False)


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


async def get_auth_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthContext:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise AuthenticationError("Missing or invalid Authorization header.")

    access_token = credentials.credentials

    try:
        supabase = await create_supabase_user_client(settings, access_token)
        user = await supabase.auth.get_user()
    except AuthApiError as exc:
        raise_for_auth_error(exc, "Invalid or expired auth token.")
    except AppError:
        # Let app errors (ConfigurationError, etc.) bubble up with correct status codes.
        raise
    except Exception as exc:
        # Unexpected errors (network issues, timeouts, etc.)
        raise ExternalServiceError("Failed to validate auth token.") from exc

    user_id = _extract_user_id(user)
    if not user_id:
        raise AuthenticationError("Invalid auth token.")

    return AuthContext(access_token=access_token, user_id=user_id)

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError, ExternalServiceError
from app.services.supabase import create_supabase_user_client

security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    access_token: str
    user_id: str


def get_auth_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthContext:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise AuthenticationError("Missing or invalid Authorization header.")

    access_token = credentials.credentials

    try:
        supabase = create_supabase_user_client(settings, access_token)
        user = supabase.auth.get_user()
    except AuthenticationError:
        raise
    except Exception as exc:
        # In practice Supabase may return different error types; we keep the surface stable.
        raise ExternalServiceError("Failed to validate auth token.") from exc

    user_id = getattr(user, "id", None) or getattr(getattr(user, "user", None), "id", None)
    if not user_id:
        raise AuthenticationError("Invalid auth token.")

    return AuthContext(access_token=access_token, user_id=str(user_id))

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthenticatedUser:
    """Application identity produced by the HTTP authentication boundary."""

    access_token: str
    user_id: str

"""Application settings loaded from environment variables."""

from __future__ import annotations

import json
from functools import lru_cache
from ipaddress import ip_address, ip_network
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_SUPABASE_DB_PORT = 5432
DEFAULT_WORKER_MAX_CONCURRENT_JOBS = 10


class Settings(BaseSettings):
    """
    Configuration loaded from environment variables.

    Only secrets and deployment-specific values belong here.
    Application constants live in their respective modules.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------------------------------------------------------------------------
    # API Keys (required secrets)
    # ---------------------------------------------------------------------------
    openrouter_api_key: str = Field(..., validation_alias="OPENROUTER_API_KEY")
    groq_api_key: str = Field(..., validation_alias="GROQ_API_KEY")

    # ---------------------------------------------------------------------------
    # Supabase (required secrets)
    # ---------------------------------------------------------------------------
    supabase_url: str = Field(..., validation_alias="SUPABASE_URL")
    supabase_publishable_key: str = Field(..., validation_alias="SUPABASE_PUBLISHABLE_KEY")
    supabase_secret_key: str = Field(..., validation_alias="SUPABASE_SECRET_KEY")
    supabase_db_password: str | None = Field(default=None, validation_alias="SUPABASE_DB_PASSWORD")
    supabase_db_user: str = Field(default="postgres", validation_alias="SUPABASE_DB_USER")
    supabase_db_name: str = Field(default="postgres", validation_alias="SUPABASE_DB_NAME")
    supabase_db_host: str | None = Field(default=None, validation_alias="SUPABASE_DB_HOST")
    supabase_db_port: int = Field(
        default=DEFAULT_SUPABASE_DB_PORT,
        validation_alias="SUPABASE_DB_PORT",
        ge=1,
        le=65_535,
    )

    # ---------------------------------------------------------------------------
    # Environment config (optional)
    # ---------------------------------------------------------------------------
    app_env: Literal["local", "test", "staging", "production"] = Field(
        default="local",
        validation_alias="APP_ENV",
    )

    # ---------------------------------------------------------------------------
    # Deployment config (optional)
    # ---------------------------------------------------------------------------
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        validation_alias="CORS_ALLOW_ORIGINS",
    )
    rate_limit: int = Field(
        default=0,
        validation_alias="RATE_LIMIT",
        ge=0,
        le=100_000,
    )  # requests/min, 0 = disabled locally only
    trust_proxy_headers: bool = Field(default=False, validation_alias="TRUST_PROXY_HEADERS")
    trusted_proxy_networks: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        validation_alias="TRUSTED_PROXY_NETWORKS",
    )
    explore_operator_user_ids: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        validation_alias="EXPLORE_OPERATOR_USER_IDS",
    )
    polar_access_token: str | None = Field(default=None, validation_alias="POLAR_ACCESS_TOKEN")
    polar_webhook_secret: str | None = Field(default=None, validation_alias="POLAR_WEBHOOK_SECRET")
    polar_success_url: str | None = Field(default=None, validation_alias="POLAR_SUCCESS_URL")
    polar_checkout_return_url: str | None = Field(default=None, validation_alias="POLAR_CHECKOUT_RETURN_URL")
    polar_portal_return_url: str | None = Field(default=None, validation_alias="POLAR_PORTAL_RETURN_URL")
    polar_server: str = Field(default="sandbox", validation_alias="POLAR_SERVER")
    worker_max_concurrent_jobs: int = Field(
        default=DEFAULT_WORKER_MAX_CONCURRENT_JOBS,
        validation_alias="WORKER_MAX_CONCURRENT_JOBS",
        ge=1,
        le=64,
    )

    @field_validator(
        "openrouter_api_key",
        "groq_api_key",
        "supabase_url",
        "supabase_publishable_key",
        "supabase_secret_key",
        "supabase_db_password",
        "supabase_db_user",
        "supabase_db_name",
        "supabase_db_host",
        "app_env",
        "polar_access_token",
        "polar_webhook_secret",
        "polar_success_url",
        "polar_checkout_return_url",
        "polar_portal_return_url",
        "polar_server",
        mode="before",
    )
    @classmethod
    def _strip_strings(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator(
        "cors_allow_origins",
        "trusted_proxy_networks",
        "explore_operator_user_ids",
        mode="before",
    )
    @classmethod
    def _parse_list(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            if value.lstrip().startswith("["):
                try:
                    decoded = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise ValueError("List settings must be comma-separated values or a JSON array.") from exc
                if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
                    raise ValueError("List settings JSON values must be arrays of strings.")
                return decoded
            items = [item.strip() for item in value.split(",")]
            return [item for item in items if item]
        return value

    @field_validator("cors_allow_origins")
    @classmethod
    def _validate_cors_origins(cls, origins: list[str]) -> list[str]:
        normalized: list[str] = []
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                origin == "*"
                or "*" in origin
                or parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise ValueError(
                    "CORS_ALLOW_ORIGINS entries must be exact http(s) origins without wildcards, credentials, or paths."
                )
            normalized_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
            if normalized_origin not in normalized:
                normalized.append(normalized_origin)
        return normalized

    @field_validator("trusted_proxy_networks")
    @classmethod
    def _validate_proxy_networks(cls, networks: list[str]) -> list[str]:
        normalized: list[str] = []
        for network in networks:
            try:
                parsed = ip_network(network, strict=False)
            except ValueError as exc:
                raise ValueError("TRUSTED_PROXY_NETWORKS entries must be IP addresses or CIDR networks.") from exc
            normalized_network = str(parsed)
            if normalized_network not in normalized:
                normalized.append(normalized_network)
        return normalized

    @field_validator("explore_operator_user_ids")
    @classmethod
    def _validate_explore_operator_user_ids(cls, user_ids: list[str]) -> list[str]:
        normalized: list[str] = []
        for user_id in user_ids:
            try:
                normalized_user_id = str(UUID(user_id))
            except ValueError as exc:
                raise ValueError("EXPLORE_OPERATOR_USER_IDS entries must be UUIDs.") from exc
            if normalized_user_id not in normalized:
                normalized.append(normalized_user_id)
        return normalized

    @model_validator(mode="after")
    def _validate_runtime_security(self) -> Self:
        has_proxy_networks = bool(self.trusted_proxy_networks)
        if self.trust_proxy_headers != has_proxy_networks:
            raise ValueError("TRUST_PROXY_HEADERS and TRUSTED_PROXY_NETWORKS must be enabled or disabled together.")

        if not self.is_strict_runtime:
            return self

        if self.rate_limit <= 0:
            raise ValueError("RATE_LIMIT must be greater than zero when APP_ENV is staging or production.")
        if not self.cors_allow_origins:
            raise ValueError("CORS_ALLOW_ORIGINS is required when APP_ENV is staging or production.")

        for origin in self.cors_allow_origins:
            parsed = urlsplit(origin)
            if parsed.scheme != "https":
                raise ValueError("CORS_ALLOW_ORIGINS must use https when APP_ENV is staging or production.")
            hostname = parsed.hostname or ""
            if _is_loopback_hostname(hostname):
                raise ValueError("Loopback CORS origins are not allowed in staging or production.")

        _require_secure_service_url(self.supabase_url, variable_name="SUPABASE_URL")
        for variable_name, value in (
            ("POLAR_SUCCESS_URL", self.polar_success_url),
            ("POLAR_CHECKOUT_RETURN_URL", self.polar_checkout_return_url),
            ("POLAR_PORTAL_RETURN_URL", self.polar_portal_return_url),
        ):
            if value:
                _require_secure_service_url(value, variable_name=variable_name)

        if not self.supabase_db_host or _is_loopback_hostname(self.supabase_db_host):
            raise ValueError("SUPABASE_DB_HOST must be a non-loopback host in staging or production.")
        if not self.supabase_db_password:
            raise ValueError("SUPABASE_DB_PASSWORD is required when APP_ENV is staging or production.")

        if self.app_env == "production" and self.polar_server != "production":
            raise ValueError("POLAR_SERVER must be production when APP_ENV is production.")

        return self

    @property
    def is_strict_runtime(self) -> bool:
        return self.app_env in {"staging", "production"}


def _is_loopback_hostname(hostname: str) -> bool:
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


def _require_secure_service_url(value: str, *, variable_name: str) -> None:
    parsed = urlsplit(value)
    hostname = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or not hostname
        or _is_loopback_hostname(hostname)
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(f"{variable_name} must be an absolute non-loopback https URL in staging or production.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

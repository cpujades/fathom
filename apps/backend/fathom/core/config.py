"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_BILLING_DEBT_CAP_SECONDS = 600
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
    supabase_db_port: int = DEFAULT_SUPABASE_DB_PORT

    # ---------------------------------------------------------------------------
    # Environment config (optional)
    # ---------------------------------------------------------------------------
    app_env: str = Field(default="local", validation_alias="APP_ENV")

    # ---------------------------------------------------------------------------
    # Deployment config (optional)
    # ---------------------------------------------------------------------------
    cors_allow_origins: list[str] = Field(default_factory=list, validation_alias="CORS_ALLOW_ORIGINS")
    rate_limit: int = Field(default=0, validation_alias="RATE_LIMIT")  # requests/min, 0 = disabled
    trust_proxy_headers: bool = Field(default=False, validation_alias="TRUST_PROXY_HEADERS")
    polar_access_token: str | None = Field(default=None, validation_alias="POLAR_ACCESS_TOKEN")
    polar_webhook_secret: str | None = Field(default=None, validation_alias="POLAR_WEBHOOK_SECRET")
    polar_success_url: str | None = Field(default=None, validation_alias="POLAR_SUCCESS_URL")
    polar_checkout_return_url: str | None = Field(default=None, validation_alias="POLAR_CHECKOUT_RETURN_URL")
    polar_portal_return_url: str | None = Field(default=None, validation_alias="POLAR_PORTAL_RETURN_URL")
    polar_server: str = Field(default="sandbox", validation_alias="POLAR_SERVER")
    billing_debt_cap_seconds: int = DEFAULT_BILLING_DEBT_CAP_SECONDS
    worker_max_concurrent_jobs: int = DEFAULT_WORKER_MAX_CONCURRENT_JOBS

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

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _parse_list(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",")]
            return [item for item in items if item]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

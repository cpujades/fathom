"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    supabase_jwt_secret: str | None = Field(default=None, validation_alias="SUPABASE_JWT_SECRET")
    supabase_db_password: str | None = Field(default=None, validation_alias="SUPABASE_DB_PASSWORD")
    supabase_db_user: str = Field(default="postgres", validation_alias="SUPABASE_DB_USER")
    supabase_db_name: str = Field(default="postgres", validation_alias="SUPABASE_DB_NAME")
    supabase_db_host: str | None = Field(default=None, validation_alias="SUPABASE_DB_HOST")
    supabase_db_port: int = Field(default=5432, validation_alias="SUPABASE_DB_PORT")

    # ---------------------------------------------------------------------------
    # Environment config (optional)
    # ---------------------------------------------------------------------------
    app_env: str = Field(default="local", validation_alias="APP_ENV")

    # ---------------------------------------------------------------------------
    # Deployment config (optional)
    # ---------------------------------------------------------------------------
    cors_allow_origins: list[str] = Field(default_factory=list, validation_alias="CORS_ALLOW_ORIGINS")
    rate_limit: int = Field(default=0, validation_alias="RATE_LIMIT")  # requests/min, 0 = disabled
    worker_max_concurrent_jobs: int = Field(default=10, validation_alias="WORKER_MAX_CONCURRENT_JOBS")
    worker_job_notify_timeout_seconds: float = Field(
        default=10.0,
        validation_alias="WORKER_JOB_NOTIFY_TIMEOUT_SECONDS",
    )

    @field_validator(
        "openrouter_api_key",
        "groq_api_key",
        "supabase_url",
        "supabase_publishable_key",
        "supabase_secret_key",
        "supabase_jwt_secret",
        "supabase_db_password",
        "supabase_db_user",
        "supabase_db_name",
        "supabase_db_host",
        "app_env",
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

    @field_validator("worker_max_concurrent_jobs", mode="before")
    @classmethod
    def _clamp_worker_jobs(cls, value: object) -> object:
        if isinstance(value, int):
            return max(1, value)
        return value

    @field_validator("worker_job_notify_timeout_seconds", mode="before")
    @classmethod
    def _clamp_worker_timeout(cls, value: object) -> object:
        if isinstance(value, (int, float)):
            return max(1.0, float(value))
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

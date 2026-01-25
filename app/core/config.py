from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deepgram_api_key: str = Field(..., validation_alias="DEEPGRAM_API_KEY")
    openrouter_api_key: str = Field(..., validation_alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="openai/gpt-4.1-mini", validation_alias="OPENROUTER_MODEL")
    openrouter_site_url: str | None = Field(default=None, validation_alias="OPENROUTER_SITE_URL")
    openrouter_app_name: str | None = Field(default="fathom", validation_alias="OPENROUTER_APP_NAME")

    supabase_url: str = Field(..., validation_alias="SUPABASE_URL")
    supabase_publishable_key: str = Field(..., validation_alias="SUPABASE_PUBLISHABLE_KEY")
    supabase_secret_key: str = Field(..., validation_alias="SUPABASE_SECRET_KEY")
    supabase_bucket: str = Field(default="fathom", validation_alias="SUPABASE_BUCKET")
    supabase_signed_url_ttl_seconds: int = Field(default=3600, validation_alias="SUPABASE_SIGNED_URL_TTL_SECONDS")
    worker_poll_interval_seconds: int = Field(default=2, validation_alias="WORKER_POLL_INTERVAL_SECONDS")
    worker_idle_sleep_seconds: int = Field(default=5, validation_alias="WORKER_IDLE_SLEEP_SECONDS")
    worker_max_attempts: int = Field(default=3, validation_alias="WORKER_MAX_ATTEMPTS")
    worker_backoff_base_seconds: int = Field(default=5, validation_alias="WORKER_BACKOFF_BASE_SECONDS")
    worker_stale_after_seconds: int = Field(default=900, validation_alias="WORKER_STALE_AFTER_SECONDS")

    @field_validator(
        "deepgram_api_key",
        "openrouter_api_key",
        "openrouter_model",
        "supabase_url",
        "supabase_publishable_key",
        "supabase_secret_key",
        "supabase_bucket",
        mode="before",
    )
    @classmethod
    def _strip_required_strings(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("openrouter_site_url", "openrouter_app_name", mode="before")
    @classmethod
    def _normalize_optional_strings(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

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
    deepgram_api_key: str = Field(..., validation_alias="DEEPGRAM_API_KEY")
    openrouter_api_key: str = Field(..., validation_alias="OPENROUTER_API_KEY")

    # ---------------------------------------------------------------------------
    # Supabase (required secrets + deployment config)
    # ---------------------------------------------------------------------------
    supabase_url: str = Field(..., validation_alias="SUPABASE_URL")
    supabase_publishable_key: str = Field(..., validation_alias="SUPABASE_PUBLISHABLE_KEY")
    supabase_secret_key: str = Field(..., validation_alias="SUPABASE_SECRET_KEY")
    supabase_bucket: str = Field(default="fathom", validation_alias="SUPABASE_BUCKET")

    # ---------------------------------------------------------------------------
    # Deployment config (optional)
    # ---------------------------------------------------------------------------
    cors_allow_origins: list[str] = Field(default_factory=list, validation_alias="CORS_ALLOW_ORIGINS")
    rate_limit: int = Field(default=0, validation_alias="RATE_LIMIT")  # requests/min, 0 = disabled

    @field_validator(
        "deepgram_api_key",
        "openrouter_api_key",
        "supabase_url",
        "supabase_publishable_key",
        "supabase_secret_key",
        "supabase_bucket",
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

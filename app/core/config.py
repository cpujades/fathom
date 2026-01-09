import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    deepgram_api_key: str
    openrouter_api_key: str
    openrouter_model: str
    openrouter_site_url: str | None
    openrouter_app_name: str | None
    supabase_url: str
    supabase_publishable_key: str
    supabase_secret_key: str
    supabase_bucket: str
    supabase_signed_url_ttl_seconds: int


def get_settings() -> Settings:
    return Settings(
        deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", "").strip(),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini").strip(),
        openrouter_site_url=os.getenv("OPENROUTER_SITE_URL", "").strip() or None,
        openrouter_app_name=os.getenv("OPENROUTER_APP_NAME", "fathom").strip() or None,
        supabase_url=os.getenv("SUPABASE_URL", "").strip(),
        supabase_publishable_key=os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip(),
        supabase_secret_key=os.getenv("SUPABASE_SECRET_KEY", "").strip(),
        supabase_bucket=os.getenv("SUPABASE_BUCKET", "fathom").strip(),
        supabase_signed_url_ttl_seconds=int(os.getenv("SUPABASE_SIGNED_URL_TTL_SECONDS", "3600")),
    )

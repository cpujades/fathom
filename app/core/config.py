import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    deepgram_api_key: str
    openrouter_api_key: str
    openrouter_model: str
    openrouter_site_url: str | None
    openrouter_app_name: str | None
    output_dir: str


def get_settings() -> Settings:
    return Settings(
        deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", "").strip(),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini").strip(),
        openrouter_site_url=os.getenv("OPENROUTER_SITE_URL", "").strip() or None,
        openrouter_app_name=os.getenv("OPENROUTER_APP_NAME", "fathom").strip() or None,
        output_dir=os.getenv("OUTPUT_DIR", "./data").strip(),
    )

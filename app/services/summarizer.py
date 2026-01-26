from __future__ import annotations

from typing import Any

from openai import APIError, OpenAI

from app.core.constants import SYSTEM_PROMPT
from app.core.errors import ExternalServiceError


class SummarizationError(ExternalServiceError):
    pass


def summarize_transcript(
    transcript: str,
    api_key: str,
    model: str,
    site_url: str | None,
    app_name: str | None,
) -> str:
    if not api_key:
        raise SummarizationError("Missing OPENROUTER_API_KEY.")

    headers: dict[str, str] = {}
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers=headers or None,
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
            temperature=0.2,
        )
    except APIError as exc:
        raise SummarizationError("Failed to call OpenRouter.") from exc

    content: Any = response.choices[0].message.content if response.choices else None
    if not isinstance(content, str) or not content.strip():
        raise SummarizationError("Empty summary response.")

    return content.strip()

from __future__ import annotations

from typing import Any

from openai import APIError, AsyncOpenAI

from app.core.constants import SYSTEM_PROMPT
from app.core.errors import ExternalServiceError

# Default OpenRouter model for summarization
OPENROUTER_MODEL = "x-ai/grok-4.1-fast"

# OpenRouter metadata headers (optional but recommended)
OPENROUTER_APP_NAME = "fathom"


class SummarizationError(ExternalServiceError):
    pass


async def summarize_transcript(transcript: str, api_key: str) -> str:
    if not api_key:
        raise SummarizationError("Missing OPENROUTER_API_KEY.")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "X-Title": OPENROUTER_APP_NAME,
        },
    )

    try:
        response = await client.chat.completions.create(
            model=OPENROUTER_MODEL,
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

from __future__ import annotations

from typing import Any

from fathom.core.errors import ExternalServiceError


class TranscriptionError(ExternalServiceError):
    pass


def _extract_groq_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if not isinstance(text, str):
        raise TranscriptionError("Groq response missing text.")
    if not text.strip():
        raise TranscriptionError("Empty transcript.")
    return text


def transcribe_url(media_url: str, api_key: str, model: str) -> str:
    if not api_key:
        raise TranscriptionError("Missing GROQ_API_KEY.")

    try:
        from groq import Groq
    except ImportError as exc:
        raise TranscriptionError("Groq client is not installed.") from exc

    client = Groq(api_key=api_key)
    response = client.audio.transcriptions.create(
        url=media_url,
        model=model,
        response_format="json",
        temperature=0.0,
    )
    return _extract_groq_text(response)

from __future__ import annotations

import asyncio
import pathlib
from typing import Any, NoReturn

from deepgram import AsyncDeepgramClient
from deepgram.core.api_error import ApiError

from app.core.errors import ExternalServiceError

# Default Deepgram model for transcription
DEEPGRAM_MODEL = "nova-2"


class TranscriptionError(ExternalServiceError):
    pass


def _raise_for_deepgram_error(exc: ApiError) -> NoReturn:
    """Convert Deepgram ApiError to TranscriptionError with request context."""
    request_id = (exc.headers or {}).get("dg-request-id") or (exc.headers or {}).get("x-request-id")
    raise TranscriptionError(
        f"Deepgram transcription failed (status_code={exc.status_code}, request_id={request_id})."
    ) from exc


def _extract_transcript(response: Any) -> str:
    """Extract and validate transcript text from Deepgram response."""
    try:
        transcript = response.results.channels[0].alternatives[0].transcript
    except (AttributeError, IndexError, TypeError) as exc:
        raise TranscriptionError("Failed to parse transcript response.") from exc

    if not isinstance(transcript, str):
        raise TranscriptionError("Transcript response was not a string.")
    if not transcript.strip():
        raise TranscriptionError("Empty transcript.")

    return transcript


async def transcribe_file(file_path: pathlib.Path, api_key: str) -> str:
    if not api_key:
        raise TranscriptionError("Missing DEEPGRAM_API_KEY.")

    audio_bytes = await asyncio.to_thread(file_path.read_bytes)
    client = AsyncDeepgramClient(api_key=api_key)

    try:
        response = await client.listen.v1.media.transcribe_file(
            request=audio_bytes,
            model=DEEPGRAM_MODEL,
            smart_format=True,
            punctuate=True,
        )
    except ApiError as exc:
        _raise_for_deepgram_error(exc)

    return _extract_transcript(response)


async def transcribe_url(media_url: str, api_key: str) -> str:
    if not api_key:
        raise TranscriptionError("Missing DEEPGRAM_API_KEY.")

    client = AsyncDeepgramClient(api_key=api_key)

    try:
        response = await client.listen.v1.media.transcribe_url(
            url=media_url,
            model=DEEPGRAM_MODEL,
            smart_format=True,
            punctuate=True,
        )
    except ApiError as exc:
        _raise_for_deepgram_error(exc)

    return _extract_transcript(response)

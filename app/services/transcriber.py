from __future__ import annotations

import asyncio
import pathlib

from deepgram import AsyncDeepgramClient
from deepgram.core.api_error import ApiError

from app.core.errors import ExternalServiceError


class TranscriptionError(ExternalServiceError):
    pass


async def transcribe_file(file_path: pathlib.Path, api_key: str, model: str) -> str:
    if not api_key:
        raise TranscriptionError("Missing DEEPGRAM_API_KEY.")
    if not model:
        raise TranscriptionError("Missing DEEPGRAM_MODEL.")

    audio_bytes = await asyncio.to_thread(file_path.read_bytes)
    client = AsyncDeepgramClient(api_key=api_key)
    try:
        response = await client.listen.v1.media.transcribe_file(
            request=audio_bytes,
            model=model,
            smart_format=True,
            punctuate=True,
        )
    except ApiError as exc:
        request_id = (exc.headers or {}).get("dg-request-id") or (exc.headers or {}).get("x-request-id")
        raise TranscriptionError(
            f"Deepgram transcription failed (status_code={exc.status_code}, request_id={request_id})."
        ) from exc
    except Exception as exc:
        raise TranscriptionError("Unexpected error while calling Deepgram.") from exc

    try:
        transcript = response.results.channels[0].alternatives[0].transcript
    except Exception as exc:
        raise TranscriptionError("Failed to parse transcript response.") from exc

    if not isinstance(transcript, str):
        raise TranscriptionError("Transcript response was not a string.")
    if not transcript.strip():
        raise TranscriptionError("Empty transcript.")

    return transcript


async def transcribe_url(media_url: str, api_key: str, model: str) -> str:
    if not api_key:
        raise TranscriptionError("Missing DEEPGRAM_API_KEY.")
    if not model:
        raise TranscriptionError("Missing DEEPGRAM_MODEL.")

    client = AsyncDeepgramClient(api_key=api_key)

    try:
        response = await client.listen.v1.media.transcribe_url(
            url=media_url,
            model=model,
            smart_format=True,
            punctuate=True,
        )
    except ApiError as exc:
        request_id = (exc.headers or {}).get("dg-request-id") or (exc.headers or {}).get("x-request-id")
        raise TranscriptionError(
            f"Deepgram transcription failed (status_code={exc.status_code}, request_id={request_id})."
        ) from exc
    except Exception as exc:
        raise TranscriptionError("Unexpected error while calling Deepgram.") from exc

    try:
        transcript = response.results.channels[0].alternatives[0].transcript
    except Exception as exc:
        raise TranscriptionError("Failed to parse transcript response.") from exc

    if not isinstance(transcript, str):
        raise TranscriptionError("Transcript response was not a string.")
    if not transcript.strip():
        raise TranscriptionError("Empty transcript.")

    return transcript

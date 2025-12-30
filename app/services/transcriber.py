from __future__ import annotations

import pathlib

from deepgram import DeepgramClient
from deepgram.core.api_error import ApiError

from app.core.errors import ExternalServiceError


class TranscriptionError(ExternalServiceError):
    pass


def transcribe_file(file_path: pathlib.Path, api_key: str) -> str:
    if not api_key:
        raise TranscriptionError("Missing DEEPGRAM_API_KEY.")

    client = DeepgramClient(api_key=api_key)

    with open(file_path, "rb") as audio_file:
        audio_bytes = audio_file.read()

    try:
        response = client.listen.v1.media.transcribe_file(
            request=audio_bytes,
            model="nova-2",
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

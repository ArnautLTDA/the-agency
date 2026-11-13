"""Groq Whisper audio transcription client (:3007)."""

import base64
from typing import Any
import httpx
from loguru import logger
from pydantic import BaseModel

from config import settings


class TranscriptionResult(BaseModel):
    """Result of audio speech-to-text transcription."""

    text: str
    duration_seconds: float | None = None
    confidence: float = 1.0


class WhisperClient:
    """Client for Groq Whisper transcription API (TC-109)."""

    def __init__(
        self,
        api_key: str = settings.GROQ_API_KEY,
        api_base: str = settings.GROQ_API_BASE,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self._client = client

    async def transcribe_audio_bytes(
        self,
        audio_bytes: bytes,
        filename: str = "voice_note.ogg",
        mime_type: str = "audio/ogg",
    ) -> TranscriptionResult:
        """Sends audio bytes to Groq Whisper endpoint and returns transcribed text."""
        url = f"{self.api_base}/audio/transcriptions"
        client = self._client or httpx.AsyncClient(timeout=15.0)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        files = {
            "file": (filename, audio_bytes, mime_type),
        }
        data = {
            "model": settings.WHISPER_MODEL,
            "response_format": "json",
            "temperature": "0.0",
        }

        try:
            resp = await client.post(url, headers=headers, files=files, data=data)
            resp.raise_for_status()
            res_json = resp.json()
            transcribed_text = res_json.get("text", "").strip()
            duration = res_json.get("duration")

            logger.info("Transcribed audio successfully ({len_text} chars)", len_text=len(transcribed_text))
            return TranscriptionResult(
                text=transcribed_text,
                duration_seconds=float(duration) if duration is not None else None,
            )
        except httpx.HTTPError as exc:
            logger.error("Groq Whisper API HTTP error: {err}", err=exc)
            raise
        finally:
            if self._client is None:
                await client.aclose()

    async def transcribe_base64(
        self,
        audio_base64: str,
        mime_type: str = "audio/ogg",
    ) -> TranscriptionResult:
        """Decodes base64 string and transcribes."""
        audio_bytes = base64.b64decode(audio_base64)
        return await self.transcribe_audio_bytes(audio_bytes, mime_type=mime_type)

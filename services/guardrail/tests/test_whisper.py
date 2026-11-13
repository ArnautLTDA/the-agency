"""Tests for Whisper Audio Transcription (TC-109)."""

import base64
import pytest
import respx

from services.whisper import WhisperClient


@pytest.mark.asyncio
async def test_transcribe_audio_bytes_success_tc109():
    """TC-109: Transcribes audio bytes into text via Groq Whisper API."""
    with respx.mock(base_url="https://api.groq.com/openai/v1") as mock:
        mock.post("/audio/transcriptions").respond(
            200,
            json={
                "text": "Olá, gostaria de saber os horários disponíveis para barba amanhã.",
                "duration": 3.45,
            },
        )

        client = WhisperClient(api_key="mock-key")
        dummy_audio = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00"
        result = await client.transcribe_audio_bytes(dummy_audio, filename="audio.ogg")

        assert "horários disponíveis" in result.text
        assert result.duration_seconds == 3.45
        assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_transcribe_base64():
    """Verifies decoding base64 audio and transcribing."""
    with respx.mock(base_url="https://api.groq.com/openai/v1") as mock:
        mock.post("/audio/transcriptions").respond(
            200,
            json={"text": "Quero agendar um corte.", "duration": 2.1},
        )

        client = WhisperClient(api_key="mock-key")
        audio_b64 = base64.b64encode(b"dummy audio content").decode("utf-8")
        result = await client.transcribe_base64(audio_b64)

        assert result.text == "Quero agendar um corte."
        assert result.duration_seconds == 2.1

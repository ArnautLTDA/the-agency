"""Tests for Guardrail MCP Server tools and FastAPI endpoints."""

import base64
from fastapi.testclient import TestClient
import pytest
import respx

from main import app
from mcp_server import create_guardrail_mcp_server
from services.llama_guard import LlamaGuardClient
from services.whisper import WhisperClient


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_mcp_inspect_content_tool():
    """Executes inspect_content via MCP server."""
    with respx.mock(base_url="https://api.groq.com/openai/v1") as mock:
        mock.post("/chat/completions").respond(
            200,
            json={"choices": [{"message": {"content": "safe"}}]},
        )

        server = create_guardrail_mcp_server(
            llama_guard_client=LlamaGuardClient(api_key="mock")
        )
        res = await server.call_tool("inspect_content", {"text": "Olá, tudo bem?"})
        assert res is not None
        assert len(res.content) > 0


@pytest.mark.asyncio
async def test_mcp_transcribe_audio_tool():
    """Executes transcribe_audio via MCP server."""
    with respx.mock(base_url="https://api.groq.com/openai/v1") as mock:
        mock.post("/audio/transcriptions").respond(
            200,
            json={"text": "Áudio transcrito com sucesso.", "duration": 1.5},
        )

        server = create_guardrail_mcp_server(
            whisper_client=WhisperClient(api_key="mock")
        )
        audio_b64 = base64.b64encode(b"audio data").decode("utf-8")
        res = await server.call_tool("transcribe_audio", {"audio_base64": audio_b64})
        assert res is not None
        assert len(res.content) > 0


def test_health_endpoint_public(client: TestClient):
    """Health check endpoint is publicly accessible."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
    assert resp.json()["service"] == "guardrail-gateway"
    assert resp.json()["port"] == 3007


def test_auth_middleware_blocks_unauthorized_post(client: TestClient):
    """Non-exempt routes reject requests without X-Agency-Key."""
    resp = client.post("/api/v1/guardrail/inspect", json={"text": "hello"})
    assert resp.status_code == 401
    assert resp.json()["error"] == "missing_or_invalid_agency_key"


def test_inspect_endpoint_with_valid_key(client: TestClient):
    """Valid key allows access to inspect endpoint."""
    with respx.mock(base_url="https://api.groq.com/openai/v1") as mock:
        mock.post("/chat/completions").respond(
            200,
            json={"choices": [{"message": {"content": "safe"}}]},
        )
        resp = client.post(
            "/api/v1/guardrail/inspect",
            json={"text": "Olá, quanto é o serviço?"},
            headers={"X-Agency-Key": "agency_dev_secret_key_12345"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_safe"] is True


def test_transcribe_endpoint_with_valid_key(client: TestClient):
    """Valid key allows access to transcribe endpoint."""
    with respx.mock(base_url="https://api.groq.com/openai/v1") as mock:
        mock.post("/audio/transcriptions").respond(
            200,
            json={"text": "Transcrição realizada.", "duration": 2.0},
        )
        resp = client.post(
            "/api/v1/whisper/transcribe",
            files={"file": ("test.ogg", b"audio data", "audio/ogg")},
            headers={"X-Agency-Key": "agency_dev_secret_key_12345"},
        )
        assert resp.status_code == 200
        assert "Transcrição" in resp.json()["text"]

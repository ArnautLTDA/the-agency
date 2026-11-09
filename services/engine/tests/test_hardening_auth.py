"""Tests for API Key Authentication, CORS and Request ID Hardening (TC-041 to TC-044, TC-072, TC-073)."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.config import get_settings
from src.main import create_app
from src.models.database import create_db_and_tables, get_async_engine, init_db


@pytest_asyncio.fixture
async def app_instance():
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_auth.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"
        engine = get_async_engine(db_url)
        await create_db_and_tables(engine)
        init_db(db_url)
        app = create_app(db_url=db_url)
        yield app
        await engine.dispose()


@pytest.mark.asyncio
async def test_tc041_auth_happy_path(app_instance):
    """TC-041: Request with valid X-Engine-Key is authorized and accepted."""
    settings = get_settings()
    transport = ASGITransport(app=app_instance)
    headers = {"X-Engine-Key": settings.ENGINE_API_KEY}

    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        with patch("src.runner.agent_runner.AgentRunner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "Task complete"
            payload = {
                "agent_id": "homologation_agent",
                "task": "Authorized task",
                "workspace_dir": "workspaces/clients/default",
            }
            res = await client.post("/api/v1/agent/run", json=payload)
            assert res.status_code == 202
            assert res.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_tc042_auth_missing_header_rejected(app_instance):
    """TC-042: Request without X-Engine-Key header is rejected with 401 Unauthorized."""
    transport = ASGITransport(app=app_instance)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "agent_id": "homologation_agent",
            "task": "Unauthorized task",
        }
        res = await client.post("/api/v1/agent/run", json=payload)
        assert res.status_code == 401
        assert "Missing or invalid API key" in res.json()["detail"]


@pytest.mark.asyncio
async def test_tc043_auth_invalid_header_rejected(app_instance):
    """TC-043: Request with wrong X-Engine-Key is rejected with 401 Unauthorized."""
    transport = ASGITransport(app=app_instance)
    headers = {"X-Engine-Key": "wrong-secret-key"}

    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        payload = {
            "agent_id": "homologation_agent",
            "task": "Task with wrong key",
        }
        res = await client.post("/api/v1/agent/run", json=payload)
        assert res.status_code == 401
        assert "Missing or invalid API key" in res.json()["detail"]


@pytest.mark.asyncio
async def test_tc044_auth_constant_time_comparison(app_instance):
    """TC-044: Verification uses secrets.compare_digest preventing timing attacks."""
    with patch("secrets.compare_digest", return_value=True) as mock_compare:
        from src.api.auth import verify_api_key

        result = await verify_api_key(api_key="valid-test-key")
        assert result == "valid-test-key"
        assert mock_compare.called


@pytest.mark.asyncio
async def test_tc072_request_id_middleware_propagation(app_instance):
    """TC-072: Requests receive and propagate X-Request-ID header."""
    transport = ASGITransport(app=app_instance)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Without incoming X-Request-ID (should be generated)
        res = await client.get("/api/v1/health")
        assert res.status_code == 200
        assert "X-Request-ID" in res.headers
        generated_id = res.headers["X-Request-ID"]
        assert len(generated_id) > 10

        # With explicit incoming X-Request-ID (should be preserved)
        custom_id = "custom-trace-uuid-12345"
        res_custom = await client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
        assert res_custom.status_code == 200
        assert res_custom.headers["X-Request-ID"] == custom_id


@pytest.mark.asyncio
async def test_tc073_cors_policy_headers(app_instance):
    """TC-073: Allowed CORS origins receive Access-Control headers."""
    transport = ASGITransport(app=app_instance)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Preflight from allowed origin
        res = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"

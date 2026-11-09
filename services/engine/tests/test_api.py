"""Tests for FastAPI HTTP Endpoints (TC-007, TC-008, TC-012 to TC-017)."""

import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from src.config import get_settings
from src.main import create_app
from src.models.database import create_db_and_tables, get_async_engine, get_session, get_session_factory, init_db
from src.models.entities import AgentRun, RunStatus


@pytest_asyncio.fixture
async def app_with_db():
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_api.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"
        engine = get_async_engine(db_url)
        await create_db_and_tables(engine)
        init_db(db_url)
        app = create_app(db_url=db_url)
        yield app, db_url
        await engine.dispose()


@pytest.mark.asyncio
async def test_tc007_health_check_healthy(app_with_db):
    """TC-007: GET /api/v1/health returns 200 OK when database and components are healthy."""
    app, _ = app_with_db
    auth_headers = {"X-Engine-Key": get_settings().ENGINE_API_KEY}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as client:
        res = await client.get("/api/v1/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "usd_brl_rate" in data


@pytest.mark.asyncio
async def test_tc008_health_check_degraded(app_with_db):
    """TC-008: GET /api/v1/health returns 503 when database is inaccessible."""
    app, _ = app_with_db

    async def broken_session():
        mock_s = AsyncMock()
        mock_s.exec.side_effect = Exception("Simulated DB connection failure")
        yield mock_s

    app.dependency_overrides[get_session] = broken_session
    auth_headers = {"X-Engine-Key": get_settings().ENGINE_API_KEY}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as client:
        res = await client.get("/api/v1/health")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_tc012_agent_run_dispatch_202_accepted(app_with_db):
    """TC-012: POST /api/v1/agent/run accepts valid task and returns 202 immediately with run_id."""
    app, db_url = app_with_db
    auth_headers = {"X-Engine-Key": get_settings().ENGINE_API_KEY}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as client:
        with patch("src.runner.agent_runner.AgentRunner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "Task complete"
            payload = {
                "agent_id": "homologation_agent",
                "task": "Test dispatch task",
                "workspace_dir": "workspaces/clients/default",
            }
            res = await client.post("/api/v1/agent/run", json=payload)
            assert res.status_code == 202
            data = res.json()
            assert "run_id" in data
            assert data["status"] == "queued"
            assert "stream_url" in data


@pytest.mark.asyncio
async def test_tc013_agent_run_non_existent_agent(app_with_db):
    """TC-013: POST /api/v1/agent/run returns 404 for unknown agent_id."""
    app, _ = app_with_db
    auth_headers = {"X-Engine-Key": get_settings().ENGINE_API_KEY}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as client:
        payload = {
            "agent_id": "ghost_non_existent_agent",
            "task": "Test task",
        }
        res = await client.post("/api/v1/agent/run", json=payload)
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_tc014_agent_run_invalid_payload(app_with_db):
    """TC-014: POST /api/v1/agent/run with empty prompt or missing required fields returns 422."""
    app, _ = app_with_db
    auth_headers = {"X-Engine-Key": get_settings().ENGINE_API_KEY}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as client:
        # Empty body
        res = await client.post("/api/v1/agent/run", json={})
        assert res.status_code == 422

        # Empty prompt
        res = await client.post("/api/v1/agent/run", json={"agent_id": "homologation_agent", "task": ""})
        assert res.status_code == 422


@pytest.mark.asyncio
async def test_tc015_agent_run_giant_prompt(app_with_db):
    """TC-015: POST /api/v1/agent/run rejects giant prompts exceeding 100k characters with 422/413."""
    app, _ = app_with_db
    auth_headers = {"X-Engine-Key": get_settings().ENGINE_API_KEY}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as client:
        huge_task = "A" * 100001
        res = await client.post(
            "/api/v1/agent/run",
            json={"agent_id": "homologation_agent", "task": huge_task},
        )
        assert res.status_code in [413, 422]


@pytest.mark.asyncio
async def test_tc016_get_agent_run_status(app_with_db):
    """TC-016: GET /api/v1/agent/run/{run_id} returns run progress and telemetry."""
    app, db_url = app_with_db
    engine = get_async_engine(db_url)
    session_factory = get_session_factory(engine)
    run_id = uuid.uuid4()

    async with session_factory() as session:
        session.add(
            AgentRun(
                run_id=run_id,
                agent_id="homologation_agent",
                task="Checking run",
                status=RunStatus.RUNNING,
                iterations=3,
                total_prompt_tokens=150,
                total_completion_tokens=45,
                total_cost_usd=0.0002,
                total_cost_brl=0.0011,
            )
        )
        await session.commit()
    await engine.dispose()

    auth_headers = {"X-Engine-Key": get_settings().ENGINE_API_KEY}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as client:
        res = await client.get(f"/api/v1/agent/run/{run_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["run_id"] == str(run_id)
        assert data["status"] == "running"
        assert data["iterations"] == 3
        assert data["total_cost_usd"] == 0.0002


@pytest.mark.asyncio
async def test_tc017_get_non_existent_run(app_with_db):
    """TC-017: GET /api/v1/agent/run/{unknown_id} returns 404."""
    app, _ = app_with_db
    auth_headers = {"X-Engine-Key": get_settings().ENGINE_API_KEY}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as client:
        unknown_id = uuid.uuid4()
        res = await client.get(f"/api/v1/agent/run/{unknown_id}")
        assert res.status_code == 404

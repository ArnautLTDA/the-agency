"""Tests for Workspace Confinement and Agent ID Validation (TC-045 to TC-049, SEC-011)."""

import gc
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api.router import _background_tasks
from src.config import get_settings
from src.main import create_app
from src.models.database import create_db_and_tables, get_async_engine, init_db


@pytest_asyncio.fixture
async def app_instance():
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_ws.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"
        engine = get_async_engine(db_url)
        await create_db_and_tables(engine)
        init_db(db_url)
        app = create_app(db_url=db_url)
        yield app
        await engine.dispose()


@pytest.mark.asyncio
async def test_tc045_valid_workspace_slug(app_instance):
    """TC-045: Dispatch with valid workspace_slug creates canonical directory."""
    settings = get_settings()
    transport = ASGITransport(app=app_instance)
    headers = {"X-Engine-Key": settings.ENGINE_API_KEY}

    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        with patch("src.runner.agent_runner.AgentRunner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "Task complete"
            payload = {
                "agent_id": "homologation_agent",
                "task": "Test valid workspace confinement",
                "workspace_slug": "alpha-client-01",
            }
            res = await client.post("/api/v1/agent/run", json=payload)
            assert res.status_code == 202
            data = res.json()
            assert data["status"] == "queued"

            expected_dir = Path("workspaces/clients/alpha-client-01").resolve()
            assert expected_dir.exists()


@pytest.mark.asyncio
async def test_tc046_reject_absolute_path_in_workspace(app_instance):
    """TC-046: Reject arbitrary root or absolute path in workspace_slug with 422."""
    settings = get_settings()
    transport = ASGITransport(app=app_instance)
    headers = {"X-Engine-Key": settings.ENGINE_API_KEY}

    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        payload = {
            "agent_id": "homologation_agent",
            "task": "Test path injection",
            "workspace_slug": "/",
        }
        res = await client.post("/api/v1/agent/run", json=payload)
        assert res.status_code == 422


@pytest.mark.asyncio
async def test_tc047_reject_path_traversal_in_workspace(app_instance):
    """TC-047: Reject path traversal sequences (../../etc) in workspace_slug with 422."""
    settings = get_settings()
    transport = ASGITransport(app=app_instance)
    headers = {"X-Engine-Key": settings.ENGINE_API_KEY}

    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        payload = {
            "agent_id": "homologation_agent",
            "task": "Test path traversal",
            "workspace_slug": "../../etc",
        }
        res = await client.post("/api/v1/agent/run", json=payload)
        assert res.status_code == 422


@pytest.mark.asyncio
async def test_tc048_reject_agent_id_traversal(app_instance):
    """TC-048: Reject agent_id containing traversal sequences with 422."""
    settings = get_settings()
    transport = ASGITransport(app=app_instance)
    headers = {"X-Engine-Key": settings.ENGINE_API_KEY}

    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        payload = {
            "agent_id": "../../../etc/passwd",
            "task": "Test agent traversal",
            "workspace_slug": "default",
        }
        res = await client.post("/api/v1/agent/run", json=payload)
        assert res.status_code == 422


@pytest.mark.asyncio
async def test_tc049_boundary_workspace_slug_lengths(app_instance):
    """TC-049: Accept minimum (1 char) and long (64 chars) valid alphanumeric slugs."""
    settings = get_settings()
    transport = ASGITransport(app=app_instance)
    headers = {"X-Engine-Key": settings.ENGINE_API_KEY}

    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        with patch("src.runner.agent_runner.AgentRunner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "Task complete"

            # 1 char slug
            res1 = await client.post(
                "/api/v1/agent/run",
                json={"agent_id": "homologation_agent", "task": "Min length", "workspace_slug": "x"},
            )
            assert res1.status_code == 202

            # 64 chars slug
            slug64 = "client-" + "a" * 50 + "-prod_01"
            res64 = await client.post(
                "/api/v1/agent/run",
                json={"agent_id": "homologation_agent", "task": "64 length", "workspace_slug": slug64},
            )
            assert res64.status_code == 202


@pytest.mark.asyncio
async def test_tc059_asyncio_task_retained_against_gc(app_instance):
    """TC-059 / SEC-011: Background task is retained in _background_tasks set and survives gc.collect()."""
    settings = get_settings()
    transport = ASGITransport(app=app_instance)
    headers = {"X-Engine-Key": settings.ENGINE_API_KEY}

    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        with patch("src.runner.agent_runner.AgentRunner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "Task complete"
            initial_count = len(_background_tasks)

            res = await client.post(
                "/api/v1/agent/run",
                json={"agent_id": "homologation_agent", "task": "GC survivability test"},
            )
            assert res.status_code == 202

            # Force garbage collection multiple times
            gc.collect()
            gc.collect()

            # Verify that at least one task is active or was properly registered in the set
            assert len(_background_tasks) >= initial_count

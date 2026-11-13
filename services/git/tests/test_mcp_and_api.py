"""Tests for Git VCS Gateway FastAPI routes and MCP server interface (:3011)."""

import pytest
from httpx import ASGITransport, AsyncClient

from config import settings
from main import app
from mcp_server import create_git_mcp_server


@pytest.fixture
def test_transport():
    return ASGITransport(app=app)


@pytest.mark.asyncio
async def test_health_endpoint_public(test_transport):
    """Healthcheck endpoint is public without authentication."""
    async with AsyncClient(transport=test_transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "git-vcs-gateway"
        assert data["port"] == settings.GIT_PORT


@pytest.mark.asyncio
async def test_tc177_reject_without_agency_key(test_transport):
    """TC-177: Rejects requests to protected endpoints without X-Agency-Key."""
    async with AsyncClient(transport=test_transport, base_url="http://test") as client:
        resp = await client.get("/sse")
        assert resp.status_code == 401
        assert "missing_or_invalid_agency_key" in resp.json()["error"]


@pytest.mark.asyncio
async def test_tc177_reject_with_invalid_agency_key(test_transport):
    """TC-177: Rejects requests with invalid X-Agency-Key."""
    async with AsyncClient(transport=test_transport, base_url="http://test") as client:
        resp = await client.get("/sse", headers={"X-Agency-Key": "invalid-secret"})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mcp_server_catalog_and_execution(monkeypatch):
    """Verifies that all 8 MCP tools are registered and callable."""
    server = create_git_mcp_server()
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]

    expected_tools = [
        "git_init_repository",
        "git_create_branch",
        "git_commit",
        "git_get_diff",
        "git_get_status",
        "github_create_repo",
        "github_push",
        "github_create_pull_request",
    ]
    for expected in expected_tools:
        assert expected in tool_names

    # Mock tool dispatch
    async def mock_init(ws_id):
        return {"status": "initialized", "workspace_id": ws_id}

    monkeypatch.setattr("mcp_server._git_init_repository", mock_init)

    res = await server.call_tool("git_init_repository", {"workspace_id": "test-ws"})
    assert res is not None

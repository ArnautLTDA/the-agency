"""Tests for Cloud Deploy Gateway MCP Server and FastAPI endpoints."""

from unittest.mock import AsyncMock, MagicMock
import aiosqlite
from fastapi.testclient import TestClient
import pytest
import respx

from main import app
from mcp_server import create_deploy_mcp_server
from supabase_client import DatabaseProvisionResult, SupabaseClient
from vercel_client import DeploymentResult, VercelClient


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoints_public(client: TestClient):
    """Health endpoints are exempt from X-Agency-Key."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
    assert resp.json()["service"] == "deploy-cloud-gateway"
    assert resp.json()["port"] == 3012


def test_protected_route_without_key_is_rejected(client: TestClient):
    """Non-exempt routes reject requests missing X-Agency-Key."""
    resp = client.get("/sse")
    assert resp.status_code == 401
    assert resp.json()["error"] == "missing_or_invalid_agency_key"


@pytest.mark.asyncio
async def test_mcp_deploy_preview_demo():
    """Executes deploy_preview_demo via MCP server."""
    mock_vercel = MagicMock(spec=VercelClient)
    mock_vercel.create_deployment = AsyncMock(
        return_value=DeploymentResult(
            id="dep_prev_1",
            url="https://preview.vercel.app",
            ready_state="READY",
            target="preview",
        )
    )

    server = create_deploy_mcp_server(vercel_client=mock_vercel)
    res = await server.call_tool("deploy_preview_demo", {"workspace_id": "ws-1", "project_name": "preview-app"})

    assert res is not None
    assert len(res.content) > 0


@pytest.mark.asyncio
async def test_mcp_deploy_production_blocked_by_triple_gate(temp_db: str):
    """Executes deploy_production via MCP server and verifies Triple Gate block."""
    mock_vercel = MagicMock(spec=VercelClient)
    server = create_deploy_mcp_server(vercel_client=mock_vercel, db_path=temp_db)

    # Lead has no payment or QA records
    res = await server.call_tool(
        "deploy_production",
        {
            "workspace_id": "ws_test",
            "project_name": "vintage-prod",
            "lead_id": "lead_unpaid",
            "force_override": False,
        },
    )

    assert res is not None
    assert "Triple Gate Rejected" in res.content[0].text


@pytest.mark.asyncio
async def test_mcp_deploy_production_allowed_with_override(temp_db: str):
    """Executes deploy_production via MCP server with emergency override."""
    mock_vercel = MagicMock(spec=VercelClient)
    mock_vercel.create_deployment = AsyncMock(
        return_value=DeploymentResult(
            id="dep_prod_9",
            url="https://vintage.com.br",
            ready_state="READY",
            target="production",
        )
    )

    server = create_deploy_mcp_server(vercel_client=mock_vercel, db_path=temp_db)

    res = await server.call_tool(
        "deploy_production",
        {
            "workspace_id": "ws_test",
            "project_name": "vintage-prod",
            "lead_id": "lead_override",
            "custom_domain": "https://vintage.com.br",
            "force_override": True,
        },
    )

    assert res is not None
    assert "vintage.com.br" in res.content[0].text

    # Verify recorded in deployments table
    async with aiosqlite.connect(temp_db) as db:
        async with db.execute("SELECT deployment_url, status FROM deployments WHERE lead_id = 'lead_override'") as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == "https://vintage.com.br"
            assert row[1] == "SUCCESS"


@pytest.mark.asyncio
async def test_mcp_provision_database_and_env_tools():
    """Executes provision_database and set_project_env_vars via MCP."""
    mock_supabase = MagicMock(spec=SupabaseClient)
    mock_supabase.provision_database = AsyncMock(
        return_value=DatabaseProvisionResult(
            project_id="sb_123",
            project_name="vintage-db",
            region="sa-east-1",
            db_host="db.sb_123.supabase.co",
            status="ACTIVE_HEALTHY",
        )
    )

    mock_vercel = MagicMock(spec=VercelClient)
    mock_vercel.get_deployment = AsyncMock(
        return_value=DeploymentResult(id="dep_1", url="https://app.vercel.app", ready_state="READY", target="preview")
    )
    mock_vercel.set_project_env_vars = AsyncMock(return_value={"created_count": 1})

    server = create_deploy_mcp_server(vercel_client=mock_vercel, supabase_client=mock_supabase)

    res_db = await server.call_tool("provision_database", {"project_name": "vintage-db"})
    assert res_db is not None

    res_env = await server.call_tool("set_project_env_vars", {"project_name": "vintage-db", "env_vars": {"A": "B"}})
    assert res_env is not None

    res_stat = await server.call_tool("get_deployment_status", {"deployment_id": "dep_1"})
    assert res_stat is not None


def test_app_lifespan():
    """Verify application lifespan startup and shutdown."""
    with TestClient(app) as test_client:
        resp = test_client.get("/api/v1/health")
        assert resp.status_code == 200


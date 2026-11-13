"""Tests for Browser Gateway MCP Server tools and FastAPI endpoints."""

from fastapi.testclient import TestClient
import pytest
import respx

from browser_pool import BrowserPool
from main import app
from mcp_server import create_browser_mcp_server


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoints_public(client: TestClient):
    """Health endpoints are exempt from X-Agency-Key."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
    assert resp.json()["service"] == "browser-gateway"
    assert resp.json()["port"] == 3014


def test_protected_route_without_key_is_rejected(client: TestClient):
    """Non-exempt routes reject requests missing X-Agency-Key."""
    resp = client.get("/sse")
    assert resp.status_code == 401
    assert resp.json()["error"] == "missing_or_invalid_agency_key"


@pytest.mark.asyncio
async def test_mcp_all_tools_execution():
    """Executes all registered MCP tools on browser server."""
    with respx.mock(base_url="https://preview.agency.dev") as mock:
        mock.get("/").respond(200, html="<h1>Landing Page</h1>")

        server = create_browser_mcp_server(browser_pool=BrowserPool())

        # Screenshot
        res_shot = await server.call_tool(
            "browser_screenshot",
            {"url": "https://preview.agency.dev", "viewport_width": 375, "viewport_height": 812, "device_scale_factor": 3.0},
        )
        assert res_shot is not None

        # Inspect Console
        res_insp = await server.call_tool("browser_inspect_console", {"url": "https://preview.agency.dev"})
        assert res_insp is not None

        # Interact
        res_act = await server.call_tool("browser_interact", {"url": "https://preview.agency.dev", "actions": [{"type": "click", "selector": "#btn"}]})
        assert res_act is not None

        # Run E2E
        res_e2e = await server.call_tool("browser_run_e2e_tests", {"workspace_id": "ws-123"})
        assert res_e2e is not None

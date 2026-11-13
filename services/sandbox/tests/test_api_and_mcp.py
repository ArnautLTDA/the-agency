"""Unit tests for Workspace Sandbox MCP Server and FastAPI endpoints (TC-177)."""

import os
from fastapi.testclient import TestClient
import pytest

from agency_common.auth import HEADER_AGENCY_KEY
from main import app
from mcp_server import create_sandbox_mcp_server


def test_api_health_endpoint():
    """Verifies that /api/v1/health responds 200 without requiring X-Agency-Key."""
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "workspace-sandbox-service"
    assert data["port"] == 3010
    assert "docker_status" in data


def test_mcp_server_lists_all_tools():
    """Verifies that MCPServer registers all 5 required tools."""
    server = create_sandbox_mcp_server()
    # In MCPServer, list_tools returns tools registered
    assert server.name == "workspace-sandbox-service"
    tools = [t.name for t in server._tool_manager.list_tools()]
    assert "read_file" in tools
    assert "write_file" in tools
    assert "patch_file" in tools
    assert "list_directory" in tools
    assert "run_terminal_command" in tools


@pytest.mark.asyncio
async def test_mcp_server_direct_tool_invocation(tmp_path):
    """Verifies calling read_file and write_file directly through MCPServer."""
    old_root = os.environ.get("WORKSPACES_ROOT")
    os.environ["WORKSPACES_ROOT"] = str(tmp_path)
    try:
        server = create_sandbox_mcp_server()

        # Call write_file
        write_res = await server.call_tool(
            "write_file",
            {"workspace_id": "test_mcp", "path": "file.txt", "content": "mcp works"},
        )
        assert len(write_res.content) > 0
        assert "Successfully wrote" in write_res.content[0].text

        # Call read_file
        read_res = await server.call_tool(
            "read_file",
            {"workspace_id": "test_mcp", "path": "file.txt"},
        )
        assert len(read_res.content) > 0
        assert read_res.content[0].text == "mcp works"
    finally:
        if old_root:
            os.environ["WORKSPACES_ROOT"] = old_root
        else:
            os.environ.pop("WORKSPACES_ROOT", None)

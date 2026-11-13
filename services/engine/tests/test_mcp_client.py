"""Unit tests for engine MCPClientHost and sandbox client integration (TC-177)."""

import pytest
from mcp.server.mcpserver import MCPServer

from src.tools.mcp_client import (
    DEFAULT_SANDBOX_MCP_URL,
    MCPClientHost,
    get_sandbox_mcp_client,
    set_sandbox_mcp_client,
)


@pytest.fixture
def sample_mcp_server():
    """Provides a dummy in-memory MCPServer for test isolation."""
    server = MCPServer(name="test-mcp-server")

    @server.tool(name="read_file")
    def read_file(workspace_id: str, path: str) -> str:
        return f"content of {path} in {workspace_id}"

    @server.tool(name="write_file")
    def write_file(workspace_id: str, path: str, content: str) -> str:
        return f"wrote {len(content)} to {path}"

    return server


@pytest.mark.asyncio
async def test_mcp_client_list_tools(sample_mcp_server):
    """Verifies list_tools discovers registered tools."""
    client = MCPClientHost(in_memory_server=sample_mcp_server)
    tools = await client.list_tools()
    assert "read_file" in tools
    assert "write_file" in tools


@pytest.mark.asyncio
async def test_mcp_client_call_tool(sample_mcp_server):
    """Verifies call_tool executes tool and returns text response."""
    client = MCPClientHost(in_memory_server=sample_mcp_server)
    res = await client.call_tool("read_file", {"workspace_id": "ws-1", "path": "index.html"})
    assert res == "content of index.html in ws-1"

    res_write = await client.call_tool(
        "write_file", {"workspace_id": "ws-1", "path": "app.js", "content": "hello"}
    )
    assert res_write == "wrote 5 to app.js"


def test_sandbox_mcp_client_singleton(sample_mcp_server):
    """Verifies get_sandbox_mcp_client and set_sandbox_mcp_client."""
    orig_client = get_sandbox_mcp_client()
    assert orig_client.base_url == DEFAULT_SANDBOX_MCP_URL

    custom = MCPClientHost(in_memory_server=sample_mcp_server)
    set_sandbox_mcp_client(custom)
    assert get_sandbox_mcp_client() == custom

    # Restore
    set_sandbox_mcp_client(orig_client)


@pytest.mark.asyncio
async def test_execute_tool_dispatches_via_mcp_client(sample_mcp_server, tmp_path):
    """Verifies execute_tool dynamically routes file operations to MCP client."""
    from src.tools.registry import execute_tool

    orig_client = get_sandbox_mcp_client()
    mcp_host = MCPClientHost(in_memory_server=sample_mcp_server)
    set_sandbox_mcp_client(mcp_host)

    try:
        res = await execute_tool(
            name="read_file",
            arguments={"path": "main.py"},
            workspace_dir=tmp_path,
        )
        assert f"content of main.py in {tmp_path.name}" == res

        res_write = await execute_tool(
            name="write_file",
            arguments={"path": "main.py", "content": "print(1)"},
            workspace_dir=tmp_path,
        )
        assert f"wrote 8 to main.py" == res_write
    finally:
        set_sandbox_mcp_client(orig_client)


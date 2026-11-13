"""MCP Client Host for connecting to Agency MCP microservices via SSE (TC-177)."""

import os
from typing import Any
from loguru import logger
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

from agency_common.auth import HEADER_AGENCY_KEY, get_agency_secret_key


DEFAULT_SANDBOX_MCP_URL: str = "http://127.0.0.1:3010/sse"


class MCPClientHost:
    """Async MCP Client managing SSE connection and remote tool invocation."""

    def __init__(
        self,
        base_url: str = DEFAULT_SANDBOX_MCP_URL,
        api_key: str | None = None,
        in_memory_server: Any | None = None,
    ) -> None:
        if base_url == DEFAULT_SANDBOX_MCP_URL:
            self.base_url = os.environ.get("SANDBOX_MCP_URL", base_url)
        else:
            self.base_url = base_url
        self.api_key = api_key or get_agency_secret_key()
        self.in_memory_server = in_memory_server

    async def list_tools(self) -> list[str]:
        """Discovers available tools on the target MCP server."""
        if self.in_memory_server is not None:
            tools = self.in_memory_server._tool_manager.list_tools()
            return [t.name for t in tools]

        headers = {HEADER_AGENCY_KEY: self.api_key}
        async with sse_client(self.base_url, headers=headers) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                return [t.name for t in tools_result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Executes a tool on the MCP server and returns the text response."""
        # In-memory execution bypass for unit tests / local development without live network daemon
        if self.in_memory_server is not None:
            result = await self.in_memory_server.call_tool(name, arguments)
            if hasattr(result, "content") and result.content:
                return result.content[0].text
            return str(result)

        headers = {HEADER_AGENCY_KEY: self.api_key}
        try:
            async with sse_client(self.base_url, headers=headers) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
                    if hasattr(result, "content") and result.content:
                        return result.content[0].text
                    return str(result)
        except Exception as exc:
            logger.error(f"Error calling MCP tool '{name}' on '{self.base_url}': {exc}")
            raise


# Global singleton client host for workspace sandbox
_sandbox_client: MCPClientHost | None = None


def get_sandbox_mcp_client() -> MCPClientHost:
    """Returns the singleton MCP client for the workspace sandbox service."""
    global _sandbox_client
    if _sandbox_client is None:
        _sandbox_client = MCPClientHost()
    return _sandbox_client


def set_sandbox_mcp_client(client: MCPClientHost) -> None:
    """Sets or overrides the sandbox MCP client (e.g. for testing)."""
    global _sandbox_client
    _sandbox_client = client

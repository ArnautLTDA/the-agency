"""Native MCP Server registering workspace and sandbox tools for The Agency (:3010)."""

from typing import Any
from mcp.server.mcpserver import MCPServer

from docker_runner import run_terminal_command as run_command_in_docker
from filesystem import (
    list_directory as fs_list_directory,
    patch_file as fs_patch_file,
    read_file as fs_read_file,
    write_file as fs_write_file,
)


def create_sandbox_mcp_server() -> MCPServer:
    """Builds and configures the workspace-sandbox-service MCP server instance."""
    server = MCPServer(
        name="workspace-sandbox-service",
        version="0.1.0",
        instructions="Official Agency Workspace & Docker Sandbox MCP Server",
    )

    @server.tool(
        name="read_file",
        description="Reads and returns the complete text content of a file within the workspace.",
    )
    def read_file(workspace_id: str, path: str) -> str:
        return fs_read_file(workspace_id, path)

    @server.tool(
        name="write_file",
        description="Creates or overwrites a file with the provided content within the workspace.",
    )
    def write_file(workspace_id: str, path: str, content: str, overwrite: bool = True) -> str:
        return fs_write_file(workspace_id, path, content, overwrite)

    @server.tool(
        name="patch_file",
        description="Surgically replaces a unique code block within a file without rewriting the whole content.",
    )
    def patch_file(workspace_id: str, path: str, target: str, replacement: str) -> dict[str, Any]:
        return fs_patch_file(workspace_id, path, target, replacement)

    @server.tool(
        name="list_directory",
        description="Lists files, directories, and file sizes within a designated workspace subpath.",
    )
    def list_directory(workspace_id: str, path: str = ".") -> dict[str, Any]:
        return fs_list_directory(workspace_id, path)

    @server.tool(
        name="run_terminal_command",
        description="Executes a command inside an ephemeral Docker container mounted only with the workspace.",
    )
    async def run_terminal_command(
        workspace_id: str,
        command: str,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        return await run_command_in_docker(workspace_id, command, timeout_seconds)

    return server

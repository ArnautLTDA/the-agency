"""Native MCP Server registering Git & GitHub VCS tools (:3011)."""

from typing import Any
from mcp.server.mcpserver import MCPServer

from git_client import (
    git_commit as _git_commit,
    git_create_branch as _git_create_branch,
    git_get_diff as _git_get_diff,
    git_get_status as _git_get_status,
    git_init_repository as _git_init_repository,
)
from github_client import GitHubClient


def create_git_mcp_server(github_client: GitHubClient | None = None) -> MCPServer:
    """Builds and configures the git-vcs-gateway MCP server instance."""
    gh_client = github_client or GitHubClient()

    server = MCPServer(
        name="git-vcs-gateway",
        version="0.1.0",
        instructions="Official Agency Git & GitHub VCS MCP Server",
    )

    @server.tool(
        name="git_init_repository",
        description="Initializes local Git repository with .gitignore and default branch main (TC-131).",
    )
    async def git_init_repository(workspace_id: str) -> dict[str, Any]:
        return await _git_init_repository(workspace_id)

    @server.tool(
        name="git_create_branch",
        description="Creates and switches to a new branch following factory conventions (feat/, fix/, test/) (TC-131).",
    )
    async def git_create_branch(workspace_id: str, branch_name: str) -> dict[str, Any]:
        return await _git_create_branch(workspace_id, branch_name)

    @server.tool(
        name="git_commit",
        description="Records conventional commit signed by granular agent role with secret scan and branch check (TC-132, TC-191, TC-192, TC-193).",
    )
    async def git_commit(
        workspace_id: str,
        message: str,
        agent_role: str = "dev",
    ) -> dict[str, Any]:
        return await _git_commit(workspace_id, message, agent_role)

    @server.tool(
        name="git_get_diff",
        description="Returns unified diff of uncommitted or staged changes for QA/Security review.",
    )
    async def git_get_diff(workspace_id: str, staged: bool = False) -> dict[str, Any]:
        return await _git_get_diff(workspace_id, staged)

    @server.tool(
        name="git_get_status",
        description="Returns modified, added, and untracked files in the workspace repository.",
    )
    async def git_get_status(workspace_id: str) -> dict[str, Any]:
        return await _git_get_status(workspace_id)

    @server.tool(
        name="github_create_repo",
        description="Creates a private or public repository on GitHub via REST API (TC-134).",
    )
    async def github_create_repo(
        repo_name: str,
        description: str = "",
        private: bool = True,
    ) -> dict[str, Any]:
        return await gh_client.create_repository(repo_name, description, private)

    @server.tool(
        name="github_push",
        description="Pushes local branch commits to remote repository with exponential backoff on transient errors (TC-135).",
    )
    async def github_push(
        workspace_id: str,
        branch_name: str,
        remote_url: str = "",
    ) -> dict[str, Any]:
        return await gh_client.push(workspace_id, branch_name, remote_url)

    @server.tool(
        name="github_create_pull_request",
        description="Opens a Pull Request towards develop/main with merge conflict detection (TC-134, TC-194).",
    )
    async def github_create_pull_request(
        repo_name: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "develop",
    ) -> dict[str, Any]:
        return await gh_client.create_pull_request(repo_name, title, body, head_branch, base_branch)

    return server

"""GitHub REST API v3 client with exponential backoff and conflict handling."""

import asyncio
from typing import Any
import httpx
from loguru import logger

from audit_logger import log_git_action
from config import settings
from git_client import resolve_workspace_dir, run_git_cmd


class GitHubAPIError(RuntimeError):
    """Raised when GitHub API returns unexpected error."""


class GitHubClient:
    """Encapsulates authenticated GitHub REST v3 operations."""

    def __init__(
        self,
        token: str | None = None,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.token = token or settings.GITHUB_TOKEN
        self.base_url = (base_url or settings.GITHUB_API_URL).rstrip("/")
        self.transport = transport

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "The-Agency-Git-VCS/0.1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def create_repository(
        self,
        repo_name: str,
        description: str = "",
        private: bool = True,
    ) -> dict[str, Any]:
        """Creates a private or public GitHub repository (TC-134)."""
        url = f"{self.base_url}/user/repos"
        payload = {
            "name": repo_name,
            "description": description,
            "private": private,
            "auto_init": False,
        }

        async with httpx.AsyncClient(transport=self.transport, timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=self._get_headers())
            if resp.status_code not in (200, 201):
                raise GitHubAPIError(
                    f"Failed to create GitHub repo '{repo_name}': HTTP {resp.status_code} - {resp.text}"
                )
            data = resp.json()
            return {
                "status": "created",
                "repo_name": data.get("name", repo_name),
                "full_name": data.get("full_name", repo_name),
                "html_url": data.get("html_url", ""),
                "clone_url": data.get("clone_url", ""),
                "private": data.get("private", private),
            }

    async def push(
        self,
        workspace_id: str,
        branch_name: str,
        remote_url: str = "",
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Pushes branch to remote repository with exponential backoff on transient errors (TC-135)."""
        ws_dir = resolve_workspace_dir(workspace_id)

        # Set up remote if provided
        if remote_url:
            try:
                await run_git_cmd(ws_dir, ["remote", "set-url", "origin", remote_url])
            except Exception:
                await run_git_cmd(ws_dir, ["remote", "add", "origin", remote_url])

        last_error = None
        for attempt in range(max_retries):
            try:
                logger.info(
                    "Pushing branch '{b}' for workspace '{ws}' (attempt {a}/{m})...",
                    b=branch_name,
                    ws=workspace_id,
                    a=attempt + 1,
                    m=max_retries,
                )
                output = await run_git_cmd(ws_dir, ["push", "-u", "origin", branch_name])
                await log_git_action(workspace_id, "PUSH", "system", branch_name)
                return {
                    "status": "pushed",
                    "workspace_id": workspace_id,
                    "branch": branch_name,
                    "output": output,
                }
            except Exception as exc:
                last_error = exc
                wait_time = 0.1 * (2 ** attempt)
                logger.warning(
                    "Push attempt {a} failed ({err}). Retrying in {w:.1f}s...",
                    a=attempt + 1,
                    err=exc,
                    w=wait_time,
                )
                await asyncio.sleep(wait_time)

        raise GitHubAPIError(
            f"Failed to push branch '{branch_name}' after {max_retries} attempts: {last_error}"
        )

    async def create_pull_request(
        self,
        repo_name: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "develop",
    ) -> dict[str, Any]:
        """Opens a Pull Request with merge conflict detection (TC-134, TC-194)."""
        # repo_name can be "owner/repo" or just "repo"
        endpoint = f"{self.base_url}/repos/{repo_name}/pulls"
        payload = {
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch,
        }

        async with httpx.AsyncClient(transport=self.transport, timeout=15.0) as client:
            resp = await client.post(endpoint, json=payload, headers=self._get_headers())

            if resp.status_code == 422:
                # Merge conflict or unprocessable entity
                err_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                msg = err_data.get("message", resp.text)
                return {
                    "status": "conflict",
                    "mergeable": False,
                    "error": msg,
                    "message": "Pull request cannot be cleanly merged into base branch. Rebase required by Dev Agent.",
                }

            if resp.status_code not in (200, 201):
                raise GitHubAPIError(
                    f"Failed to create PR on '{repo_name}': HTTP {resp.status_code} - {resp.text}"
                )

            data = resp.json()
            mergeable = data.get("mergeable", True)
            if mergeable is False:
                return {
                    "status": "conflict",
                    "mergeable": False,
                    "pr_number": data.get("number"),
                    "html_url": data.get("html_url", ""),
                    "message": "PR created but has merge conflicts. Rebase required.",
                }

            return {
                "status": "created",
                "pr_number": data.get("number"),
                "html_url": data.get("html_url", ""),
                "title": data.get("title", title),
                "mergeable": True,
                "state": data.get("state", "open"),
            }

"""Tests for GitHub REST API v3 client operations and resilience (TC-134, TC-135, TC-194)."""

import httpx
import pytest
import respx

from github_client import GitHubAPIError, GitHubClient


@pytest.mark.asyncio
@respx.mock
async def test_tc134_github_create_repository():
    """TC-134: Creates private repository on GitHub."""
    respx.post("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(
            201,
            json={
                "name": "clinica-sorriso",
                "full_name": "joao/clinica-sorriso",
                "html_url": "https://github.com/joao/clinica-sorriso",
                "clone_url": "https://github.com/joao/clinica-sorriso.git",
                "private": True,
            },
        )
    )

    client = GitHubClient(token="ghp_test_token")
    repo = await client.create_repository(
        repo_name="clinica-sorriso",
        description="Landing page Clinica Sorriso",
        private=True,
    )

    assert repo["status"] == "created"
    assert repo["repo_name"] == "clinica-sorriso"
    assert repo["html_url"] == "https://github.com/joao/clinica-sorriso"
    assert repo["private"] is True


@pytest.mark.asyncio
@respx.mock
async def test_tc134_github_create_pull_request_success():
    """TC-134: Opens Pull Request towards develop/main."""
    respx.post("https://api.github.com/repos/joao/clinica-sorriso/pulls").mock(
        return_value=httpx.Response(
            201,
            json={
                "number": 42,
                "html_url": "https://github.com/joao/clinica-sorriso/pull/42",
                "title": "feat: vitrine digital",
                "mergeable": True,
                "state": "open",
            },
        )
    )

    client = GitHubClient(token="ghp_test_token")
    pr = await client.create_pull_request(
        repo_name="joao/clinica-sorriso",
        title="feat: vitrine digital",
        body="Implementação da vitrine com checkout PIX",
        head_branch="feat/vitrine",
        base_branch="develop",
    )

    assert pr["status"] == "created"
    assert pr["pr_number"] == 42
    assert pr["mergeable"] is True


@pytest.mark.asyncio
@respx.mock
async def test_tc194_github_create_pull_request_conflict():
    """TC-194: Detects merge conflict and guides Dev Agent to rebase."""
    respx.post("https://api.github.com/repos/joao/clinica-sorriso/pulls").mock(
        return_value=httpx.Response(
            422,
            json={
                "message": "Validation Failed: No commits between develop and feat/vitrine",
                "errors": [{"message": "conflict"}],
            },
        )
    )

    client = GitHubClient(token="ghp_test_token")
    pr = await client.create_pull_request(
        repo_name="joao/clinica-sorriso",
        title="feat: vitrine digital",
        body="Implementação da vitrine",
        head_branch="feat/vitrine",
        base_branch="develop",
    )

    assert pr["status"] == "conflict"
    assert pr["mergeable"] is False
    assert "Rebase required" in pr["message"]


@pytest.mark.asyncio
async def test_tc135_github_push_retry_and_backoff(monkeypatch):
    """TC-135: Applies exponential backoff retry on transient push errors."""
    attempts = 0

    async def mock_run_git_cmd(cwd, args):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("Connection reset by peer")
        return "Everything up-to-date"

    monkeypatch.setattr("github_client.run_git_cmd", mock_run_git_cmd)
    monkeypatch.setattr("github_client.resolve_workspace_dir", lambda ws: "/tmp")

    client = GitHubClient(token="ghp_test")
    res = await client.push("ws-01", "feat/vitrine", max_retries=3)

    assert res["status"] == "pushed"
    assert attempts == 3

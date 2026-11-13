"""Tests for Git CLI operations, Conventional Commits, and Secret Scanning."""

from pathlib import Path
import pytest
from tempfile import TemporaryDirectory

from config import settings
from git_client import (
    git_commit,
    git_create_branch,
    git_get_diff,
    git_get_status,
    git_init_repository,
    run_git_cmd,
)


@pytest.fixture
def temp_workspace(monkeypatch):
    """Sets up an isolated temporary directory for client workspaces."""
    with TemporaryDirectory() as tmp_dir:
        monkeypatch.setattr(settings, "WORKSPACES_ROOT", tmp_dir)
        yield tmp_dir


@pytest.mark.asyncio
async def test_tc131_git_init_and_create_branch(temp_workspace):
    """TC-131: Initializes repository with .gitignore and creates branch feat/vitrine."""
    ws_id = "ws-client-01"

    # 1. Init repository
    init_res = await git_init_repository(ws_id)
    assert init_res["status"] == "initialized"
    assert init_res["default_branch"] == "main"

    ws_dir = Path(init_res["path"])
    assert (ws_dir / ".git").is_dir()
    assert (ws_dir / ".gitignore").is_file()

    # 2. Create feature branch
    branch_res = await git_create_branch(ws_id, "feat/vitrine-digital")
    assert branch_res["status"] == "created"
    assert branch_res["branch_name"] == "feat/vitrine-digital"

    current = await run_git_cmd(ws_dir, ["branch", "--show-current"])
    assert current == "feat/vitrine-digital"


@pytest.mark.asyncio
async def test_tc131_git_create_branch_invalid_prefix(temp_workspace):
    """TC-131: Rejects branch names not starting with factory conventions."""
    ws_id = "ws-client-01"
    await git_init_repository(ws_id)

    with pytest.raises(ValueError, match="Invalid branch name"):
        await git_create_branch(ws_id, "random-branch-name")


@pytest.mark.asyncio
async def test_tc132_git_commit_conventional_and_agent_author(temp_workspace):
    """TC-132 / BDD-F1-08: Records commit signed with Dev Agent and Conventional Commits."""
    ws_id = "ws-client-01"
    await git_init_repository(ws_id)
    await git_create_branch(ws_id, "feat/vitrine")

    ws_dir = Path(temp_workspace) / ws_id
    (ws_dir / "index.html").write_text("<h1>Vitrine</h1>", encoding="utf-8")

    commit_res = await git_commit(
        workspace_id=ws_id,
        message="feat: adicionar vitrine digital",
        agent_role="dev",
    )

    assert commit_res["status"] == "committed"
    assert commit_res["branch"] == "feat/vitrine"
    assert commit_res["author"] == "Dev Agent <agents+dev@theagency.ai>"
    assert len(commit_res["commit_hash"]) == 40

    # Verify author in git log
    log_author = await run_git_cmd(ws_dir, ["log", "-1", "--format=%an <%ae>"])
    assert log_author == "Dev Agent <agents+dev@theagency.ai>"


@pytest.mark.asyncio
async def test_tc133_tc193_invalid_conventional_commit_prefix(temp_workspace):
    """TC-133 & TC-193: Rejects commit messages with invalid or missing conventional prefixes."""
    ws_id = "ws-client-01"
    await git_init_repository(ws_id)
    await git_create_branch(ws_id, "feat/vitrine")

    ws_dir = Path(temp_workspace) / ws_id
    (ws_dir / "file.txt").write_text("content", encoding="utf-8")

    # Invalid prefix: update:
    with pytest.raises(ValueError, match="Invalid Conventional Commit message"):
        await git_commit(ws_id, "update: ajustes na tela", agent_role="dev")

    # Invalid prefix: bug:
    with pytest.raises(ValueError, match="Invalid Conventional Commit message"):
        await git_commit(ws_id, "bug: corrigido problema", agent_role="dev")

    # Missing prefix completely
    with pytest.raises(ValueError, match="Invalid Conventional Commit message"):
        await git_commit(ws_id, "ajustes gerais de css", agent_role="dev")


@pytest.mark.asyncio
async def test_tc192_blocked_direct_commit_on_main(temp_workspace):
    """TC-192: Blocks direct commit to main or production branch by governance."""
    ws_id = "ws-client-01"
    await git_init_repository(ws_id)

    ws_dir = Path(temp_workspace) / ws_id
    (ws_dir / "app.js").write_text("console.log('test')", encoding="utf-8")

    with pytest.raises(ValueError, match="Direct commits to 'main' branch are blocked"):
        await git_commit(ws_id, "feat: commit proibido na main", agent_role="dev")


@pytest.mark.asyncio
async def test_tc191_secret_leak_blocked_in_commit(temp_workspace):
    """TC-191 / BDD-F1-18: Aborts commit and reverts staging if hardcoded secret is detected in diff."""
    ws_id = "ws-client-01"
    await git_init_repository(ws_id)
    await git_create_branch(ws_id, "feat/auth")

    ws_dir = Path(temp_workspace) / ws_id
    leaked_code = "const GITHUB_KEY = 'ghp_1234567890abcdef1234567890abcdef123456';\n"
    (ws_dir / "secrets.js").write_text(leaked_code, encoding="utf-8")

    with pytest.raises(ValueError, match="Secret leak detected"):
        await git_commit(ws_id, "feat: adicionar autenticacao", agent_role="dev")

    # Staging should be clean / unstaged
    status = await git_get_status(ws_id)
    # The file should be untracked or modified, not committed
    assert "secrets.js" in status["untracked"] or "secrets.js" in status["modified"]


@pytest.mark.asyncio
async def test_git_get_diff_and_status(temp_workspace):
    """Verifies diff inspection and working tree status."""
    ws_id = "ws-client-01"
    await git_init_repository(ws_id)
    await git_create_branch(ws_id, "feat/landing")

    ws_dir = Path(temp_workspace) / ws_id
    (ws_dir / "page.html").write_text("<h1>Hello</h1>", encoding="utf-8")

    status = await git_get_status(ws_id)
    assert not status["is_clean"]
    assert "page.html" in status["untracked"]

    diff_unstaged = await git_get_diff(ws_id, staged=False)
    assert diff_unstaged["staged"] is False

"""Git CLI operations, Conventional Commits validation, and secret scanning."""

import asyncio
from pathlib import Path
import re
from typing import Any
from loguru import logger

from audit_logger import log_git_action
from config import settings

_CONVENTIONAL_PATTERN = re.compile(
    r"^(feat|fix|refactor|test|docs|chore|perf)(\([a-zA-Z0-9_\-./]+\))?(!)?:\s+.+$"
)

_VALID_BRANCH_PREFIXES = ("feat/", "fix/", "test/", "chore/", "refactor/")

_AGENT_AUTHORS: dict[str, str] = {
    "dev": "Dev Agent <agents+dev@theagency.ai>",
    "qa": "QA Agent <agents+qa@theagency.ai>",
    "security": "Security Agent <agents+security@theagency.ai>",
    "architect": "Architect Agent <agents+architect@theagency.ai>",
    "po": "PO Agent <agents+po@theagency.ai>",
    "cro": "CRO Agent <agents+cro@theagency.ai>",
    "cto": "CTO Agent <agents+cto@theagency.ai>",
    "ceo": "CEO Agent <agents+ceo@theagency.ai>",
}

_SECRET_PATTERNS = [
    ("AWS_KEY", re.compile(r"\b(AKIA[0-9A-Z]{16})\b")),
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY-----")),
    ("GENERIC_SECRET", re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}['\"]")),
    ("TELEGRAM_TOKEN", re.compile(r"\b\d{8,10}:[a-zA-Z0-9_-]{35}\b")),
    ("GITHUB_PAT", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,255}\b")),
]


class GitExecutionError(RuntimeError):
    """Raised when a Git command exits with non-zero status."""


def get_agent_author(agent_role: str) -> str:
    """Returns granular formatted Git author header according to agent role (TC-132, BDD-F1-08)."""
    normalized = agent_role.strip().lower()
    if normalized in _AGENT_AUTHORS:
        return _AGENT_AUTHORS[normalized]
    return f"{agent_role.capitalize()} Agent <agents+{normalized}@theagency.ai>"


def validate_conventional_commit(message: str) -> None:
    """Validates message against Conventional Commits specification (TC-133, TC-193)."""
    if not message or not message.strip():
        raise ValueError("Commit message cannot be empty.")
    first_line = message.strip().splitlines()[0]
    if not _CONVENTIONAL_PATTERN.match(first_line):
        raise ValueError(
            f"Invalid Conventional Commit message: '{first_line}'. "
            "Prefix must be one of: feat, fix, refactor, test, docs, chore, perf "
            "(e.g. 'feat: adicionar vitrine' or 'fix(auth): corrigir token')."
        )


def validate_branch_name(branch_name: str) -> None:
    """Validates that branch name follows factory naming convention (TC-131)."""
    if not any(branch_name.startswith(pfx) for pfx in _VALID_BRANCH_PREFIXES):
        raise ValueError(
            f"Invalid branch name: '{branch_name}'. "
            "Must start with one of: feat/, fix/, test/, chore/, refactor/."
        )


def scan_diff_for_secrets(diff_text: str) -> None:
    """Scans git diff for leaked tokens, API keys, and credentials (TC-191, BDD-F1-18)."""
    for line_no, line in enumerate(diff_text.splitlines(), 1):
        if not line.startswith("+") or line.startswith("+++"):
            continue
        line_content = line[1:].strip()
        for rule_id, pattern in _SECRET_PATTERNS:
            if pattern.search(line_content):
                raise ValueError(
                    f"Secret leak detected on line {line_no} matching rule '{rule_id}'. "
                    "Commit rejected to prevent credential exposure."
                )


def resolve_workspace_dir(workspace_id: str) -> Path:
    """Resolves workspace path ensuring no Path Traversal."""
    clean_id = Path(workspace_id).name
    base_dir = Path(settings.WORKSPACES_ROOT).resolve()
    target_dir = (base_dir / clean_id).resolve()
    try:
        target_dir.relative_to(base_dir)
    except ValueError:
        raise ValueError(f"Invalid workspace_id '{workspace_id}': escapes workspaces root.")
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


async def run_git_cmd(cwd: Path, args: list[str]) -> str:
    """Runs git command in cwd and returns stdout string."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace").strip()
        raise GitExecutionError(f"Git command failed: git {' '.join(args)}: {err_msg}")
    return stdout.decode("utf-8", errors="replace").strip()


async def git_init_repository(workspace_id: str) -> dict[str, Any]:
    """Initializes local Git repository and configures .gitignore and default branch main (TC-131)."""
    ws_dir = resolve_workspace_dir(workspace_id)
    await run_git_cmd(ws_dir, ["init", "-b", "main"])

    # Configure local git user if not present
    await run_git_cmd(ws_dir, ["config", "user.name", "The Agency Bot"])
    await run_git_cmd(ws_dir, ["config", "user.email", "bot@theagency.ai"])

    gitignore_path = ws_dir / ".gitignore"
    if not gitignore_path.exists():
        default_ignore = "node_modules/\n.env\n.env.local\n__pycache__/\n.venv/\ndist/\n.next/\n*.pyc\n"
        gitignore_path.write_text(default_ignore, encoding="utf-8")

    await log_git_action(workspace_id, "INIT_REPO", "system", "main")
    return {
        "status": "initialized",
        "workspace_id": workspace_id,
        "default_branch": "main",
        "path": str(ws_dir),
    }


async def git_create_branch(workspace_id: str, branch_name: str) -> dict[str, Any]:
    """Creates and checks out a new branch following factory naming (TC-131)."""
    validate_branch_name(branch_name)
    ws_dir = resolve_workspace_dir(workspace_id)

    # If repo has no commits yet, create an initial commit first so checkout -b works cleanly
    try:
        await run_git_cmd(ws_dir, ["rev-parse", "HEAD"])
    except GitExecutionError:
        await run_git_cmd(ws_dir, ["add", "-A"])
        await run_git_cmd(ws_dir, ["commit", "-m", "chore: initial repository structure", "--allow-empty"])

    await run_git_cmd(ws_dir, ["checkout", "-b", branch_name])
    await log_git_action(workspace_id, "BRANCH_CREATE", "dev", branch_name)
    return {
        "status": "created",
        "workspace_id": workspace_id,
        "branch_name": branch_name,
    }


async def git_commit(
    workspace_id: str,
    message: str,
    agent_role: str = "dev",
) -> dict[str, Any]:
    """Executes conventional commit signed with granular agent author and secret scanning (TC-132, TC-191, TC-192, TC-193)."""
    ws_dir = resolve_workspace_dir(workspace_id)

    # 1. Branch governance check: block direct commits on main or production (TC-192)
    current_branch = await run_git_cmd(ws_dir, ["branch", "--show-current"])
    if current_branch in ("main", "master", "production", "prod"):
        raise ValueError(
            f"Direct commits to '{current_branch}' branch are blocked by factory governance. "
            "Create a feature branch (e.g. feat/<name>) and open a Pull Request."
        )

    # 2. Conventional commits validation (TC-133, TC-193)
    validate_conventional_commit(message)

    # 3. Stage changes
    await run_git_cmd(ws_dir, ["add", "-A"])

    # 4. Secret scanning on staged diff (TC-191, BDD-F1-18)
    staged_diff = await run_git_cmd(ws_dir, ["diff", "--cached"])
    try:
        scan_diff_for_secrets(staged_diff)
    except ValueError as leak_exc:
        # Reset staging on secret detection
        await run_git_cmd(ws_dir, ["reset"])
        raise leak_exc

    # 5. Granular agent authorship header (TC-132, BDD-F1-08)
    author = get_agent_author(agent_role)

    # 6. Perform commit
    commit_out = await run_git_cmd(
        ws_dir,
        ["commit", "-m", message, f"--author={author}"],
    )
    commit_hash = await run_git_cmd(ws_dir, ["rev-parse", "HEAD"])

    # 7. Record in audit logs
    await log_git_action(
        workspace_id=workspace_id,
        action="COMMIT",
        agent_role=agent_role,
        branch=current_branch,
        commit_hash=commit_hash,
        message=message,
    )

    return {
        "status": "committed",
        "workspace_id": workspace_id,
        "branch": current_branch,
        "commit_hash": commit_hash,
        "author": author,
        "message": message,
        "details": commit_out,
    }


async def git_get_diff(workspace_id: str, staged: bool = False) -> dict[str, Any]:
    """Returns unified diff of uncommitted or staged changes."""
    ws_dir = resolve_workspace_dir(workspace_id)
    args = ["diff", "--cached"] if staged else ["diff"]
    diff_text = await run_git_cmd(ws_dir, args)
    return {
        "workspace_id": workspace_id,
        "staged": staged,
        "diff": diff_text,
    }


async def git_get_status(workspace_id: str) -> dict[str, Any]:
    """Returns status of working tree (modified, added, untracked)."""
    ws_dir = resolve_workspace_dir(workspace_id)
    try:
        current_branch = await run_git_cmd(ws_dir, ["branch", "--show-current"])
    except GitExecutionError:
        current_branch = "unknown"

    status_raw = await run_git_cmd(ws_dir, ["status", "--porcelain"])
    modified = []
    added = []
    untracked = []

    for line in status_raw.splitlines():
        if not line or len(line) < 3:
            continue
        code = line[:2]
        path_str = line[3:].strip()
        if code.startswith("?"):
            untracked.append(path_str)
        elif "M" in code:
            modified.append(path_str)
        elif "A" in code:
            added.append(path_str)

    return {
        "workspace_id": workspace_id,
        "branch": current_branch,
        "is_clean": len(status_raw) == 0,
        "modified": modified,
        "added": added,
        "untracked": untracked,
    }

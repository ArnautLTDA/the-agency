"""Native Agent Tools implementations conforming strictly to Phase 0 specification."""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.entities import AgentMessage, MessagePriority, MessageStatus, MessageType
from src.runner.sandbox import BaseSandboxDriver, get_sandbox_driver


class PathTraversalError(PermissionError):
    """Raised when an operation attempts to escape the authorized workspace directory."""
    pass


class CouncilSecurityError(PermissionError):
    """Raised when an autonomous agent attempts to modify immutable Council profiles."""
    pass


def resolve_safe_path(workspace_dir: Path, rel_path: str) -> Path:
    """Validates that rel_path stays strictly inside workspace_dir."""
    clean_path = rel_path.strip()
    # Check if absolute path outside workspace
    if os.path.isabs(clean_path):
        target = Path(clean_path).resolve()
    else:
        target = (workspace_dir / clean_path).resolve()

    resolved_ws = workspace_dir.resolve()
    try:
        target.relative_to(resolved_ws)
    except ValueError:
        raise PathTraversalError(f"Access denied: Path '{rel_path}' escapes workspace root.")

    # TC-011: Immutability of Council profiles
    normalized_str = target.as_posix().lower()
    if "config/agents/council" in normalized_str:
        raise CouncilSecurityError(
            "Access denied: Council profiles under config/agents/council/ are strictly immutable."
        )

    return target


def read_file(workspace_dir: Path, path: str) -> str:
    """Reads and returns text content from a file inside the authorized workspace."""
    target_file = resolve_safe_path(workspace_dir, path)
    if not target_file.exists():
        return f"Error: File not found at '{path}'."
    if target_file.is_dir():
        return f"Error: Path '{path}' is a directory, not a file."

    try:
        return target_file.read_text(encoding="utf-8")
    except Exception as exc:
        return f"Error reading file '{path}': {exc}"


def write_file(
    workspace_dir: Path,
    path: str,
    content: str,
    overwrite: bool = True,
) -> str:
    """Creates or overwrites a file inside workspace, automatically creating parent directories."""
    target_file = resolve_safe_path(workspace_dir, path)
    if target_file.exists() and not overwrite:
        return f"Error: File '{path}' already exists and overwrite=False."

    try:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(content, encoding="utf-8")
        return f"Success: File '{path}' written successfully ({len(content)} characters)."
    except Exception as exc:
        return f"Error writing file '{path}': {exc}"


def patch_file(
    workspace_dir: Path,
    path: str,
    search_block: str,
    replace_block: str,
) -> str:
    """Surgically replaces a single occurrence of search_block in a file."""
    target_file = resolve_safe_path(workspace_dir, path)
    if not target_file.exists():
        return f"Error: File not found at '{path}'."

    try:
        content = target_file.read_text(encoding="utf-8")
    except Exception as exc:
        return f"Error reading file '{path}': {exc}"

    occurrences = content.count(search_block)
    if occurrences == 0:
        return f"Error: Target block not found in '{path}'. File was not modified."
    if occurrences > 1:
        return (
            f"Error: Ambiguous match. Target block was found {occurrences} times in '{path}'. "
            "Provide a more specific search block with surrounding context."
        )

    updated_content = content.replace(search_block, replace_block, 1)
    try:
        target_file.write_text(updated_content, encoding="utf-8")
        lines_changed = len(replace_block.splitlines())
        return f"Success: Surgically patched '{path}' ({lines_changed} replacement lines)."
    except Exception as exc:
        return f"Error saving patched file '{path}': {exc}"


def list_directory(workspace_dir: Path, path: str = ".") -> list[dict[str, Any]] | str:
    """Lists files and folders inside a workspace directory with structured metadata."""
    try:
        target_dir = resolve_safe_path(workspace_dir, path)
        if not target_dir.exists():
            return f"Error: Directory '{path}' does not exist."
        if not target_dir.is_dir():
            return f"Error: Path '{path}' is a file, not a directory."

        results = []
        for item in sorted(target_dir.iterdir()):
            results.append({
                "name": item.name,
                "is_dir": item.is_dir(),
                "size": item.stat().st_size if item.is_file() else 0,
            })
        return results
    except Exception as exc:
        return f"Error listing directory '{path}': {exc}"


def run_terminal_command(
    workspace_dir: Path,
    command: str,
    timeout: int = 60,
    driver: BaseSandboxDriver | None = None,
) -> dict[str, Any]:
    """Executes a bash command inside the isolated sandbox."""
    active_driver = driver or get_sandbox_driver()
    result = active_driver.execute(command=command, cwd=workspace_dir, timeout=timeout)
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
    }


async def send_agent_message(
    session: AsyncSession,
    from_agent: str,
    to_agent: str,
    message_type: MessageType | str,
    payload: dict[str, Any],
    priority: MessagePriority | str = MessagePriority.MEDIUM,
    requires_ack: bool = False,
    correlation_id: str | None = None,
) -> str:
    """Persists a validated inter-agent message in the AgentMessage queue table."""
    try:
        valid_msg_type = (
            message_type if isinstance(message_type, MessageType) else MessageType(message_type)
        )
        valid_priority = (
            priority if isinstance(priority, MessagePriority) else MessagePriority(priority)
        )
    except ValueError as exc:
        return f"Error: Invalid message_type or priority: {exc}"

    msg = AgentMessage(
        id=uuid.uuid4(),
        timestamp=datetime.now(timezone.utc),
        from_agent=from_agent,
        to_agent=to_agent,
        message_type=valid_msg_type,
        priority=valid_priority,
        payload=payload,
        correlation_id=correlation_id,
        requires_ack=requires_ack,
        status=MessageStatus.PENDING,
    )
    session.add(msg)
    await session.commit()
    return f"Success: Message {msg.id} sent to '{to_agent}' ({valid_msg_type.value})."

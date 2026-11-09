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


def _atomic_write(target_path: Path, content: str) -> None:
    """Writes content to a temporary file in the same directory and replaces atomically (SEC-014)."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.parent / f".{target_path.name}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        temp_path.write_text(content, encoding="utf-8")
        os.replace(temp_path, target_path)
    except Exception:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        raise


def read_file(workspace_dir: Path, path: str) -> str:
    """Reads and returns text content from a file inside the authorized workspace (SEC-015)."""
    target_file = resolve_safe_path(workspace_dir, path)
    if not target_file.exists():
        return f"Error: File not found at '{path}'."
    if target_file.is_dir():
        return f"Error: Path '{path}' is a directory, not a file."

    # SEC-015: File size limit (2 MB)
    try:
        file_size = target_file.stat().st_size
    except Exception as exc:
        return f"Error inspecting file '{path}': {exc}"

    max_size = 2 * 1024 * 1024  # 2 MB
    if file_size > max_size:
        size_mb = file_size / (1024 * 1024)
        return f"Error: File '{path}' exceeds maximum readable size of 2 MB ({size_mb:.2f} MB)."

    # SEC-015: Binary detection (first 512 bytes)
    try:
        with open(target_file, "rb") as f:
            header = f.read(512)
            if b"\x00" in header:
                return f"Error: File '{path}' appears to be a binary file and cannot be read as text."
    except Exception as exc:
        return f"Error inspecting file '{path}': {exc}"

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
    """Creates or overwrites a file inside workspace using atomic replacement (SEC-014)."""
    target_file = resolve_safe_path(workspace_dir, path)
    if target_file.exists() and not overwrite:
        return f"Error: File '{path}' already exists and overwrite=False."

    try:
        _atomic_write(target_file, content)
        return f"Success: File '{path}' written successfully ({len(content)} characters)."
    except Exception as exc:
        return f"Error writing file '{path}': {exc}"


def patch_file(
    workspace_dir: Path,
    path: str,
    search_block: str,
    replace_block: str,
) -> str:
    """Surgically replaces a single occurrence of search_block in a file atomically (SEC-014)."""
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
        _atomic_write(target_file, updated_content)
        lines_changed = len(replace_block.splitlines())
        return f"Success: Surgically patched '{path}' ({lines_changed} replacement lines)."
    except Exception as exc:
        return f"Error saving patched file '{path}': {exc}"


class DirectoryListing(list):
    """Custom list holding directory entries with pagination metadata (SEC-013)."""

    def __init__(self, items: list[dict[str, Any]], total_count: int, has_more: bool = False):
        super().__init__(items)
        self.total_count = total_count
        self.has_more = has_more


def list_directory(
    workspace_dir: Path,
    path: str = ".",
    max_depth: int = 3,
    max_items: int = 500,
) -> DirectoryListing | str:
    """Lists files and folders inside a workspace directory with structured metadata and pagination (SEC-013)."""
    try:
        target_dir = resolve_safe_path(workspace_dir, path)
        if not target_dir.exists():
            return f"Error: Directory '{path}' does not exist."
        if not target_dir.is_dir():
            return f"Error: Path '{path}' is a file, not a directory."

        raw_entries = sorted(target_dir.iterdir(), key=lambda p: p.name)
        total_count = len(raw_entries)
        has_more = total_count > max_items
        selected_entries = raw_entries[:max_items]

        results = []
        for item in selected_entries:
            results.append({
                "name": item.name,
                "is_dir": item.is_dir(),
                "size": item.stat().st_size if item.is_file() else 0,
            })
        return DirectoryListing(results, total_count=total_count, has_more=has_more)
    except Exception as exc:
        return f"Error listing directory '{path}': {exc}"


def run_terminal_command(
    workspace_dir: Path,
    command: str,
    timeout: int = 60,
    driver: BaseSandboxDriver | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Executes a bash command inside the isolated sandbox."""
    active_driver = driver or get_sandbox_driver()
    result = active_driver.execute(command=command, cwd=workspace_dir, timeout=timeout, run_id=run_id)
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
    # SEC-017: Commit cycle belongs to caller/runner; do not commit prematurely inside tool
    return f"Success: Message {msg.id} sent to '{to_agent}' ({valid_msg_type.value})."

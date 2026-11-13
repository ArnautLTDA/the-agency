"""Filesystem operations with strict Path Traversal confinement for The Agency."""

import os
from pathlib import Path
from typing import Any


class PathTraversalError(ValueError):
    """Raised when a file path escapes the isolated client workspace directory."""


def get_workspaces_root() -> Path:
    """Returns the base directory where client workspaces reside."""
    root_str = os.environ.get("WORKSPACES_ROOT", "workspaces/clients")
    root_path = Path(root_str).resolve()
    root_path.mkdir(parents=True, exist_ok=True)
    return root_path


def resolve_workspace_path(workspace_id: str, relative_path: str) -> Path:
    """Resolves and validates that a relative path strictly remains inside the workspace."""
    if not workspace_id or not workspace_id.strip():
        raise ValueError("workspace_id must not be empty.")

    clean_workspace_id = Path(workspace_id).name
    workspace_dir = (get_workspaces_root() / clean_workspace_id).resolve()
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Normalize relative path
    clean_rel = relative_path.lstrip("/\\")
    target_path = (workspace_dir / clean_rel).resolve()

    try:
        # Raises ValueError if target_path is not a descendant of workspace_dir
        target_path.relative_to(workspace_dir)
    except ValueError:
        raise PathTraversalError(
            f"Path Traversal Violation: '{relative_path}' escapes workspace boundary '{workspace_dir}'."
        )

    return target_path


def read_file(workspace_id: str, path: str) -> str:
    """Reads complete text content of a file within the designated workspace."""
    target_path = resolve_workspace_path(workspace_id, path)
    if not target_path.exists():
        raise FileNotFoundError(f"File not found: '{path}' in workspace '{workspace_id}'.")
    if not target_path.is_file():
        raise IsADirectoryError(f"Target path '{path}' is a directory, not a file.")

    return target_path.read_text(encoding="utf-8")


def write_file(workspace_id: str, path: str, content: str, overwrite: bool = True) -> str:
    """Creates or overwrites a file inside the designated workspace."""
    target_path = resolve_workspace_path(workspace_id, path)

    if target_path.exists() and not overwrite:
        raise FileExistsError(f"File '{path}' already exists and overwrite is set to False.")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    return f"Successfully wrote {len(content.encode('utf-8'))} bytes to '{path}'."


def patch_file(workspace_id: str, path: str, target: str, replacement: str) -> dict[str, Any]:
    """Surgically replaces a unique code block within a file without rewriting the whole content."""
    target_path = resolve_workspace_path(workspace_id, path)
    if not target_path.exists() or not target_path.is_file():
        raise FileNotFoundError(f"File not found for patch: '{path}' in workspace '{workspace_id}'.")

    content = target_path.read_text(encoding="utf-8")
    count = content.count(target)

    if count == 0:
        raise ValueError(f"Target block not found in '{path}'. Patch aborted without modifying file.")

    if count > 1:
        raise ValueError(
            f"Target block appears {count} times in '{path}'. Provide surrounding context lines for unique matching."
        )

    new_content = content.replace(target, replacement, 1)
    target_path.write_text(new_content, encoding="utf-8")

    return {
        "status": "patched",
        "path": path,
        "replaced_chars": len(target),
        "new_chars": len(replacement),
    }


def list_directory(workspace_id: str, path: str = ".") -> dict[str, Any]:
    """Lists files and directories within a workspace subpath."""
    target_dir = resolve_workspace_path(workspace_id, path)
    if not target_dir.exists():
        raise FileNotFoundError(f"Directory not found: '{path}' in workspace '{workspace_id}'.")
    if not target_dir.is_dir():
        raise NotADirectoryError(f"Path '{path}' is not a directory.")

    entries: list[dict[str, Any]] = []
    for entry in sorted(target_dir.iterdir(), key=lambda e: (not e.is_dir(), e.name)):
        entries.append({
            "name": entry.name,
            "is_dir": entry.is_dir(),
            "size": entry.stat().st_size if entry.is_file() else 0,
        })

    return {
        "workspace_id": workspace_id,
        "path": path,
        "entries": entries,
    }

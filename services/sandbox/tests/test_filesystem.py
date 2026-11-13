"""Unit tests for Workspace Sandbox Filesystem operations (TC-125, TC-126, TC-185, TC-186, TC-187, TC-188)."""

from pathlib import Path
from tempfile import TemporaryDirectory
import os
import pytest

from filesystem import (
    PathTraversalError,
    list_directory,
    patch_file,
    read_file,
    resolve_workspace_path,
    write_file,
)


@pytest.fixture
def temp_workspaces():
    """Sets a temporary directory as WORKSPACES_ROOT for isolated testing."""
    with TemporaryDirectory() as tmp_dir:
        old_root = os.environ.get("WORKSPACES_ROOT")
        os.environ["WORKSPACES_ROOT"] = tmp_dir
        yield Path(tmp_dir)
        if old_root:
            os.environ["WORKSPACES_ROOT"] = old_root
        else:
            os.environ.pop("WORKSPACES_ROOT", None)


def test_read_and_write_file_happy_path(temp_workspaces):
    """TC-125: Verifies writing and reading files inside workspace."""
    ws = "client_alpha"
    msg = "console.log('hello world');"
    result = write_file(ws, "src/index.js", msg)
    assert "Successfully wrote" in result

    content = read_file(ws, "src/index.js")
    assert content == msg


def test_write_file_no_overwrite_error(temp_workspaces):
    """Verifies write_file with overwrite=False raises FileExistsError."""
    ws = "client_alpha"
    write_file(ws, "test.txt", "initial")
    with pytest.raises(FileExistsError):
        write_file(ws, "test.txt", "new", overwrite=False)


def test_patch_file_surgical_replacement(temp_workspaces):
    """TC-126: Verifies surgical patch replacement in a file."""
    ws = "client_beta"
    initial = "function calculate() {\n    return 10;\n}\n"
    write_file(ws, "math.js", initial)

    res = patch_file(ws, "math.js", target="return 10;", replacement="return 42;")
    assert res["status"] == "patched"

    updated = read_file(ws, "math.js")
    assert "return 42;" in updated
    assert "return 10;" not in updated


def test_patch_file_target_not_found_deterministic_failure(temp_workspaces):
    """TC-187: Verifies patch_file fails deterministically when target is missing, keeping file untouched."""
    ws = "client_beta"
    initial = "const x = 100;\n"
    write_file(ws, "config.js", initial)

    with pytest.raises(ValueError, match="Target block not found"):
        patch_file(ws, "config.js", target="const y = 200;", replacement="const z = 300;")

    # Ensure untouched
    assert read_file(ws, "config.js") == initial


def test_patch_file_ambiguous_target_failure(temp_workspaces):
    """TC-188: Verifies patch_file rejects ambiguous target blocks that appear multiple times."""
    ws = "client_gamma"
    initial = "return true;\nreturn true;\n"
    write_file(ws, "duplicate.js", initial)

    with pytest.raises(ValueError, match="appears 2 times"):
        patch_file(ws, "duplicate.js", target="return true;", replacement="return false;")

    # Ensure untouched
    assert read_file(ws, "duplicate.js") == initial


def test_list_directory_returns_structure(temp_workspaces):
    """Verifies listing directory contents."""
    ws = "client_delta"
    write_file(ws, "dir_a/file1.txt", "abc")
    write_file(ws, "dir_a/file2.txt", "12345")

    res = list_directory(ws, "dir_a")
    assert res["workspace_id"] == ws
    assert len(res["entries"]) == 2
    names = [e["name"] for e in res["entries"]]
    assert "file1.txt" in names
    assert "file2.txt" in names


def test_path_traversal_detection_and_blocking(temp_workspaces):
    """TC-185 & TC-186: Path traversal attempts must be strictly blocked with PathTraversalError."""
    ws = "client_security"

    # Attempt reading ../../etc/passwd
    with pytest.raises(PathTraversalError):
        read_file(ws, "../../etc/passwd")

    # Attempt writing outside workspace
    with pytest.raises(PathTraversalError):
        write_file(ws, "../secrets.env", "LEAK=true")

    # Attempt patching outside workspace
    with pytest.raises(PathTraversalError):
        patch_file(ws, "../system.conf", "A", "B")

    # Attempt listing outside workspace
    with pytest.raises(PathTraversalError):
        list_directory(ws, "../../")

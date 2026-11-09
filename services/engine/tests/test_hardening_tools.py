"""Tests for Tool Hardening, Atomic Writes, Binary Protection and Timeout Clamping (TC-064 to TC-068)."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import select

from src.models.database import create_db_and_tables, get_async_engine, get_session_factory
from src.models.entities import AgentMessage, MessagePriority, MessageType
from src.tools.implementations import (
    DirectoryListing,
    list_directory,
    patch_file,
    read_file,
    send_agent_message,
    write_file,
)
from src.tools.registry import execute_tool


def test_tc064_timeout_clamped_to_180s(temp_workspace: Path):
    """TC-064 / SEC-006: Tool registry clamps requested timeout of 99999s down to 180s maximum."""
    with patch("src.tools.registry.run_terminal_command") as mock_run:
        mock_run.return_value = {"stdout": "done", "stderr": "", "exit_code": 0, "timed_out": False}

        # Requesting 99999 seconds should clamp to 180s
        import asyncio
        asyncio.run(
            execute_tool(
                name="run_terminal_command",
                arguments={"command": "echo test", "timeout": 99999},
                workspace_dir=temp_workspace,
            )
        )
        assert mock_run.called
        assert mock_run.call_args.kwargs["timeout"] == 180

        # Requesting 1 second should clamp to 5s minimum
        asyncio.run(
            execute_tool(
                name="run_terminal_command",
                arguments={"command": "echo test", "timeout": 1},
                workspace_dir=temp_workspace,
            )
        )
        assert mock_run.call_args.kwargs["timeout"] == 5


def test_tc065_list_directory_pagination_limit(temp_workspace: Path):
    """TC-065 / SEC-013: Directory with 1,000 files returns at most 500 items with has_more=True."""
    target_dir = temp_workspace / "massive_dir"
    target_dir.mkdir(parents=True)

    for i in range(1000):
        (target_dir / f"file_{i:04d}.txt").touch()

    listing = list_directory(workspace_dir=temp_workspace, path="massive_dir")
    assert isinstance(listing, DirectoryListing)
    assert len(listing) == 500
    assert listing.has_more is True
    assert listing.total_count == 1000

    # Ensure normal small directory returns has_more=False
    small_dir = temp_workspace / "small_dir"
    small_dir.mkdir(parents=True)
    (small_dir / "sample.txt").touch()

    small_listing = list_directory(workspace_dir=temp_workspace, path="small_dir")
    assert len(small_listing) == 1
    assert small_listing.has_more is False
    assert small_listing.total_count == 1


def test_tc066_atomic_file_write_replaces_cleanly(temp_workspace: Path):
    """TC-066 / SEC-014: write_file and patch_file write via temporary file and replace cleanly."""
    file_path = temp_workspace / "data.txt"
    initial_content = "Original Clean Content"
    file_path.write_text(initial_content, encoding="utf-8")

    # Verify write_file successfully replaces target
    new_content = "New Atomic Content"
    res = write_file(workspace_dir=temp_workspace, path="data.txt", content=new_content, overwrite=True)
    assert "success" in res.lower()
    assert file_path.read_text(encoding="utf-8") == new_content

    # Verify that in case of error during replace, temporary file is cleaned up and original kept
    with patch("os.replace", side_effect=OSError("Disk write error")):
        fail_res = write_file(
            workspace_dir=temp_workspace,
            path="data.txt",
            content="Corrupted Partial Content",
            overwrite=True,
        )
        assert "error" in fail_res.lower()
        # Original content is untouched
        assert file_path.read_text(encoding="utf-8") == new_content
        # No orphan .tmp files left in the directory
        tmp_files = list(temp_workspace.glob("*.tmp"))
        assert len(tmp_files) == 0


def test_tc067_read_file_blocks_large_binary_files(temp_workspace: Path):
    """TC-067 / SEC-015: read_file blocks files > 2 MB and detects binary files with null bytes."""
    # 1. Reject binary file containing null bytes
    bin_file = temp_workspace / "binary.bin"
    bin_file.write_bytes(b"ELF\x00\x01\x02\x03SomeBinaryHeaderData")

    bin_res = read_file(workspace_dir=temp_workspace, path="binary.bin")
    assert "error" in bin_res.lower()
    assert "binary file" in bin_res.lower()

    # 2. Reject file larger than 2 MB
    large_file = temp_workspace / "giant.log"
    # Create sparse or 2.1 MB file
    with open(large_file, "wb") as f:
        f.seek(int(2.1 * 1024 * 1024))
        f.write(b"end")

    large_res = read_file(workspace_dir=temp_workspace, path="giant.log")
    assert "error" in large_res.lower()
    assert "exceeds maximum readable size" in large_res.lower()


@pytest.mark.asyncio
async def test_tc068_send_agent_message_does_not_prematurely_commit():
    """TC-068 / SEC-017: send_agent_message adds to session without calling commit()."""
    mock_session = MagicMock()
    # Mock AsyncSession where commit() should not be called
    mock_session.commit = MagicMock()

    result = await send_agent_message(
        session=mock_session,
        from_agent="alpha_agent",
        to_agent="beta_agent",
        message_type=MessageType.TASK_ASSIGNMENT,
        payload={"task_id": "123"},
        priority=MessagePriority.HIGH,
    )
    assert "success" in result.lower()
    assert mock_session.add.called
    assert not mock_session.commit.called

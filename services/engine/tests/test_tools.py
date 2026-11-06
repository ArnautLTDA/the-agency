"""Tests for Native Agent Tools, Path Confinement and Council Immutability (TC-011, TC-022 to TC-030)."""

import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlmodel import select

from src.models.database import create_db_and_tables, get_async_engine, get_session_factory
from src.models.entities import AgentMessage, MessagePriority, MessageType
from src.tools.implementations import (
    CouncilSecurityError,
    PathTraversalError,
    list_directory,
    patch_file,
    read_file,
    send_agent_message,
    write_file,
)


def test_tc022_read_existing_file(temp_workspace: Path):
    """TC-022: Reading existing file inside workspace returns text content."""
    sample_file = temp_workspace / "src" / "index.js"
    sample_file.parent.mkdir(parents=True)
    sample_file.write_text("console.log('hello world');", encoding="utf-8")

    result = read_file(workspace_dir=temp_workspace, path="src/index.js")
    assert result == "console.log('hello world');"


def test_tc023_read_non_existent_file(temp_workspace: Path):
    """TC-023: Reading non-existent file returns a descriptive error message for self-correction."""
    result = read_file(workspace_dir=temp_workspace, path="src/missing.txt")
    assert "error" in result.lower()
    assert "file not found" in result.lower() or "missing.txt" in result.lower()


def test_tc024_path_traversal_blocked(temp_workspace: Path):
    """TC-024: Path traversal outside workspace is blocked with PathTraversalError."""
    with pytest.raises(PathTraversalError):
        read_file(workspace_dir=temp_workspace, path="../../../../../etc/passwd")

    with pytest.raises(PathTraversalError):
        read_file(workspace_dir=temp_workspace, path="/etc/shadow")


def test_tc025_write_file_nested_directories(temp_workspace: Path):
    """TC-025: Writing file creates parent directories automatically and saves content."""
    res = write_file(
        workspace_dir=temp_workspace,
        path="docs/specs/api.md",
        content="# API Documentation\nVersion 1.0",
    )
    assert "success" in res.lower()
    saved = temp_workspace / "docs" / "specs" / "api.md"
    assert saved.exists()
    assert saved.read_text(encoding="utf-8") == "# API Documentation\nVersion 1.0"


def test_tc026_write_file_overwrite(temp_workspace: Path):
    """TC-026: Overwrites existing file when overwrite=True."""
    target = temp_workspace / "notes.txt"
    target.write_text("Old Content", encoding="utf-8")

    res = write_file(
        workspace_dir=temp_workspace,
        path="notes.txt",
        content="New Content",
        overwrite=True,
    )
    assert "success" in res.lower()
    assert target.read_text(encoding="utf-8") == "New Content"


def test_tc027_patch_file_surgical_single_block(temp_workspace: Path):
    """TC-027: Surgical code replacement replaces only target block and preserves other lines."""
    initial_code = (
        "import os\n"
        "\n"
        "def calculate_tax(amount):\n"
        "    return amount * 0.05\n"
        "\n"
        "def format_currency(val):\n"
        "    return f'R$ {val:.2f}'\n"
    )
    py_file = temp_workspace / "services.py"
    py_file.write_text(initial_code, encoding="utf-8")

    res = patch_file(
        workspace_dir=temp_workspace,
        path="services.py",
        search_block="def calculate_tax(amount):\n    return amount * 0.05",
        replace_block="def calculate_tax(amount):\n    return amount * 0.10",
    )
    assert "success" in res.lower()

    updated_code = py_file.read_text(encoding="utf-8")
    assert "return amount * 0.10" in updated_code
    assert "def format_currency(val):" in updated_code
    assert "import os" in updated_code


def test_tc028_patch_file_target_not_found(temp_workspace: Path):
    """TC-028: When search block is not found, patch aborts without modifying file."""
    initial_code = "x = 10\ny = 20\n"
    py_file = temp_workspace / "test.py"
    py_file.write_text(initial_code, encoding="utf-8")

    res = patch_file(
        workspace_dir=temp_workspace,
        path="test.py",
        search_block="z = 30",
        replace_block="z = 40",
    )
    assert "error" in res.lower()
    assert "target block not found" in res.lower()
    assert py_file.read_text(encoding="utf-8") == initial_code


def test_tc029_patch_file_ambiguous_multiple_matches(temp_workspace: Path):
    """TC-029: Rejects ambiguous search blocks that appear multiple times in the file."""
    initial_code = "val = 1\nval = 1\n"
    py_file = temp_workspace / "duplicate.py"
    py_file.write_text(initial_code, encoding="utf-8")

    res = patch_file(
        workspace_dir=temp_workspace,
        path="duplicate.py",
        search_block="val = 1",
        replace_block="val = 2",
    )
    assert "error" in res.lower()
    assert "ambiguous" in res.lower() or "multiple" in res.lower()
    assert py_file.read_text(encoding="utf-8") == initial_code


def test_tc030_list_directory(temp_workspace: Path):
    """TC-030: Returns structured listing of directory items with types and sizes."""
    (temp_workspace / "src").mkdir()
    (temp_workspace / "src" / "app.py").write_text("print('hi')", encoding="utf-8")
    (temp_workspace / "README.md").write_text("# Readme", encoding="utf-8")

    listing = list_directory(workspace_dir=temp_workspace, path=".")
    assert isinstance(listing, list)
    names = [item["name"] for item in listing]
    assert "src" in names
    assert "README.md" in names

    readme_entry = next(item for item in listing if item["name"] == "README.md")
    assert readme_entry["is_dir"] is False
    assert readme_entry["size"] > 0


def test_tc011_council_profiles_strictly_immutable(temp_workspace: Path):
    """TC-011: Attempting to write or patch council profiles is rejected with CouncilSecurityError."""
    council_dir = temp_workspace / "config" / "agents" / "council"
    council_dir.mkdir(parents=True)
    ceo_yaml = council_dir / "ceo.yaml"
    ceo_yaml.write_text("name: CEO\nmodel: gemini-2.5-pro", encoding="utf-8")

    with pytest.raises(CouncilSecurityError):
        write_file(
            workspace_dir=temp_workspace,
            path="config/agents/council/ceo.yaml",
            content="name: Hacked CEO",
            overwrite=True,
        )

    with pytest.raises(CouncilSecurityError):
        patch_file(
            workspace_dir=temp_workspace,
            path="config/agents/council/ceo.yaml",
            search_block="model: gemini-2.5-pro",
            replace_block="model: cheap-model",
        )


@pytest.mark.asyncio
async def test_send_agent_message_persists_to_db():
    """Verify send_agent_message tool stores message in AgentMessage table."""
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "msg_test.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"
        engine = get_async_engine(db_url)
        await create_db_and_tables(engine)
        session_factory = get_session_factory(engine)

        async with session_factory() as session:
            msg_res = await send_agent_message(
                session=session,
                from_agent="homologation_agent",
                to_agent="broadcast",
                message_type=MessageType.STATUS_UPDATE,
                payload={"progress": "Step 1 complete"},
                priority=MessagePriority.MEDIUM,
                requires_ack=False,
            )
            assert "success" in msg_res.lower()

        async with session_factory() as session:
            stmt = select(AgentMessage).where(AgentMessage.from_agent == "homologation_agent")
            saved = (await session.exec(stmt)).one()
            assert saved.to_agent == "broadcast"
            assert saved.message_type == MessageType.STATUS_UPDATE
            assert saved.payload["progress"] == "Step 1 complete"

        await engine.dispose()

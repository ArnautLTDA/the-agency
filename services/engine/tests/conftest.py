"""Shared pytest fixtures for the engine test suite."""

import os
from collections.abc import AsyncGenerator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession

# Ensure environment uses a test key by default if not set
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_api_key_valid_placeholder")
os.environ.setdefault("MAX_CONCURRENT_AGENTS", "5")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture
def temp_workspace() -> Path:
    """Creates a temporary workspace directory for file and sandbox tests."""
    with TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)

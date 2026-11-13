"""Pytest fixtures for Security Gateway test suite."""

import os
from pathlib import Path
import pytest
import respx
import httpx

from config import settings
from scanners.sonarqube import SonarQubeClient


@pytest.fixture
def mock_sonarqube_client():
    """Returns a SonarQubeClient backed by a mock AsyncClient."""
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    client = httpx.AsyncClient(transport=transport)
    return SonarQubeClient(base_url="http://localhost:9000", token="test-token", client=client)


@pytest.fixture
def sample_code_dir(tmp_path: Path):
    """Creates a temporary workspace with clean and vulnerable source files."""
    work_dir = tmp_path / "workspace"
    work_dir.mkdir()

    # Clean file
    clean_file = work_dir / "clean.py"
    clean_file.write_text("def hello(name: str) -> str:\n    return f'Hello, {name}'\n", encoding="utf-8")

    return work_dir

"""Tests for Fail-Fast configuration loading and logging (TC-001, TC-002, TC-003, TC-040)."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from pydantic import ValidationError

from src.config import Settings, get_settings, setup_logging


def test_tc001_valid_config_loading():
    """TC-001: Initialization with complete environment and valid keys succeeds."""
    env_data = {
        "GEMINI_API_KEY": "valid_key_123456",
        "MAX_CONCURRENT_AGENTS": "5",
        "DATABASE_URL": "sqlite+aiosqlite:///pipeline.db",
        "HOST": "127.0.0.1",
        "PORT": "8000",
    }
    settings = Settings(**env_data)
    assert settings.GEMINI_API_KEY == "valid_key_123456"
    assert settings.MAX_CONCURRENT_AGENTS == 5
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///pipeline.db"
    assert settings.HOST == "127.0.0.1"
    assert settings.PORT == 8000


def test_tc002_missing_gemini_key_fails_fast():
    """TC-002: Initialization without GEMINI_API_KEY is rejected immediately."""
    with pytest.raises((ValidationError, ValueError)) as exc_info:
        Settings(
            GEMINI_API_KEY="",
            MAX_CONCURRENT_AGENTS=5,
        )
    assert "GEMINI_API_KEY" in str(exc_info.value) or "gemini_api_key" in str(exc_info.value).lower()


def test_tc003_anomalous_concurrency_fallback_or_reject():
    """TC-003: MAX_CONCURRENT_AGENTS with 0 or negative value is rejected or falls back safely."""
    with pytest.raises((ValidationError, ValueError)):
        Settings(
            GEMINI_API_KEY="valid_key",
            MAX_CONCURRENT_AGENTS=0,
        )

    with pytest.raises((ValidationError, ValueError)):
        Settings(
            GEMINI_API_KEY="valid_key",
            MAX_CONCURRENT_AGENTS=-3,
        )


def test_tc040_log_setup_and_rotation():
    """TC-040: Log file is created with configured rotation and formatting without leaks."""
    with TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "engine.log"
        settings = Settings(
            GEMINI_API_KEY="secret_key_to_never_leak_987",
            LOG_FILE=str(log_file),
            LOG_ROTATION="10 MB",
        )
        logger = setup_logging(settings)
        logger.info("System startup initiated successfully")

        assert log_file.exists()
        log_content = log_file.read_text(encoding="utf-8")
        assert "System startup initiated successfully" in log_content
        assert "secret_key_to_never_leak_987" not in log_content

"""Configuration module with fail-fast validation and structured logging."""

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from loguru import logger
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Fail-fast application configuration loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core LLM Credentials
    GEMINI_API_KEY: str = Field(..., description="Google Gemini API Key (mandatory)")
    GROQ_API_KEY: str | None = Field(default=None, description="Optional Groq fallback key")
    ANTHROPIC_API_KEY: str | None = Field(default=None, description="Optional Anthropic fallback key")

    # Concurrency and Execution limits
    MAX_CONCURRENT_AGENTS: int = Field(
        default=5,
        gt=0,
        description="Maximum concurrent agent runs allowed in pool (must be > 0)",
    )
    CIRCUIT_BREAKER_MAX_ITERATIONS: int = Field(
        default=25,
        gt=0,
        description="Maximum iterations before circuit breaker trips",
    )
    TERMINAL_BUFFER_MAX_BYTES: int = Field(
        default=131072,  # 128 KB
        gt=0,
        description="Maximum bytes retained for terminal stdout/stderr before truncating",
    )

    # Database
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///pipeline.db",
        description="Async SQLite database connection string",
    )

    # Server Network Bindings
    HOST: str = Field(default="127.0.0.1", description="Server bind host")
    PORT: int = Field(default=8000, gt=0, le=65535, description="Server bind port")

    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Log level")
    LOG_FILE: str = Field(default="logs/engine.log", description="Path to operational log file")
    LOG_ROTATION: str = Field(default="10 MB", description="Rotation limit for log files")
    LOG_RETENTION: str = Field(default="30 days", description="Retention duration for logs")

    # Sandbox configuration
    DOCKER_IMAGE: str = Field(default="node:20-slim", description="Docker image for ephemeral sandbox")
    DOCKER_MEMORY_LIMIT: str = Field(default="2g", description="Memory limit for sandbox container")
    DOCKER_CPUS_LIMIT: float = Field(default=1.5, description="CPU quota for sandbox container")
    DOCKER_PIDS_LIMIT: int = Field(default=100, description="PIDs limit for sandbox container")

    # External APIs
    AWESOME_API_URL: str = Field(
        default="https://economia.awesomeapi.com.br/last/USD-BRL",
        description="Currency exchange API URL for USD/BRL",
    )

    @field_validator("GEMINI_API_KEY")
    @classmethod
    def validate_gemini_key(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("GEMINI_API_KEY must not be empty or whitespace only")
        return trimmed


def setup_logging(settings: Settings):
    """Configures Loguru with file rotation, stdout formatting, and secret masking."""
    logger.remove()

    log_path = Path(settings.LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Formatter that censors API keys if they accidentally appear
    def secret_filter(record):
        sensitive_values = [
            val
            for val in [settings.GEMINI_API_KEY, settings.GROQ_API_KEY, settings.ANTHROPIC_API_KEY]
            if val and len(val) > 4
        ]
        msg = record["message"]
        for secret in sensitive_values:
            if secret in msg:
                record["message"] = msg.replace(secret, "[REDACTED_API_KEY]")
        return True

    # Console sink
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        filter=secret_filter,
    )

    # Rotating file sink
    logger.add(
        str(log_path),
        level=settings.LOG_LEVEL,
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        filter=secret_filter,
        encoding="utf-8",
    )

    return logger


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns singleton cached instance of validated Settings."""
    try:
        return Settings()
    except Exception as exc:
        # Fail-fast during initialization if mandatory settings are missing
        sys.stderr.write(f"CRITICAL: Engine configuration failed validation: {exc}\n")
        raise

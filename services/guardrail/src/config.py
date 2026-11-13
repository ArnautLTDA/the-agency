"""Configuration settings for Guardrail Gateway (:3007)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class GuardrailSettings(BaseSettings):
    """Runtime configuration loaded from environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    GUARDRAIL_PORT: int = 3007
    GROQ_API_KEY: str = "gsk_dev_sandbox_key"
    GROQ_API_BASE: str = "https://api.groq.com/openai/v1"
    WHISPER_MODEL: str = "whisper-large-v3"
    LLAMA_GUARD_MODEL: str = "llama-guard-3-8b"
    RABBITMQ_URL: str = "amqp://agency:agency123@localhost:5672/"
    DATABASE_PATH: str = "pipeline.db"
    AGENCY_API_KEY: str = "agency-secret-key-phase1"


settings = GuardrailSettings()

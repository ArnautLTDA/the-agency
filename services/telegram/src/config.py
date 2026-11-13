"""Configuration settings for Telegram Gateway Microservice (:3008)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramSettings(BaseSettings):
    """Telegram Gateway settings loaded from environment."""

    TELEGRAM_BOT_TOKEN: str = "mock_bot_token"
    TELEGRAM_ADMIN_CHAT_ID: int = 123456789
    TELEGRAM_API_BASE: str = "https://api.telegram.org"
    ENGINE_CORE_URL: str = "http://127.0.0.1:8000"
    DATABASE_URL: str = "sqlite+aiosqlite:///../../pipeline.db"
    RABBITMQ_URL: str = "amqp://agency:agency123@127.0.0.1:5672/"
    PORT: int = 3008

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = TelegramSettings()

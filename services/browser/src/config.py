"""Configuration settings for Browser Gateway (:3014)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class BrowserSettings(BaseSettings):
    """Runtime configuration loaded from environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    BROWSER_PORT: int = 3014
    DEFAULT_TIMEOUT_MS: int = 15000
    SCREENSHOT_QUALITY: int = 90
    AGENCY_API_KEY: str = "agency-secret-key-phase1"


settings = BrowserSettings()

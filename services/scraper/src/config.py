"""Configuration settings for OSINT Scraper Gateway (:3009)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ScraperSettings(BaseSettings):
    """Runtime configuration loaded from environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    SCRAPER_PORT: int = 3009
    SEARXNG_URL: str = "http://localhost:8888"
    AGENCY_API_KEY: str = "agency-secret-key-phase1"
    MAX_PAGE_BYTES: int = 1048576  # 1 MB
    DEFAULT_TIMEOUT_SECONDS: float = 30.0
    WHATSAPP_GATEWAY_URL: str = "http://localhost:3005"


settings = ScraperSettings()

"""Configuration settings for Cloud Deploy Gateway (:3012)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class DeploySettings(BaseSettings):
    """Runtime configuration loaded from environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DEPLOY_PORT: int = 3012
    VERCEL_API_BASE: str = "https://api.vercel.com"
    VERCEL_TOKEN: str = "vercel_sandbox_token_123"
    VERCEL_TEAM_ID: str | None = None
    SUPABASE_API_BASE: str = "https://api.supabase.com"
    SUPABASE_ACCESS_TOKEN: str = "supabase_sandbox_token_123"
    DATABASE_PATH: str = "pipeline.db"
    AGENCY_API_KEY: str = "agency-secret-key-phase1"


settings = DeploySettings()

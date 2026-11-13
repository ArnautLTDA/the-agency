"""Configuration settings for Git & GitHub VCS Gateway (:3011)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class GitSettings(BaseSettings):
    """Runtime configuration for Git & GitHub VCS microservice."""

    GIT_PORT: int = 3011
    GITHUB_TOKEN: str = ""
    GITHUB_API_URL: str = "https://api.github.com"
    WORKSPACES_ROOT: str = "workspaces/clients"
    DB_PATH: str = "services/engine/pipeline.db"
    SECURITY_GATEWAY_URL: str = "http://127.0.0.1:3015"
    AGENCY_SECRET_KEY: str = "dev-agency-secret-key-12345"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = GitSettings()

"""Configuration settings for Knowledge & Memory Gateway (:3013)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class MemorySettings(BaseSettings):
    """Runtime configuration loaded from environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    MEMORY_PORT: int = 3013
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_URL: str = "http://localhost:6333"
    COLLECTION_NAME: str = "agency_knowledge"
    VECTOR_SIZE: int = 384
    SCRAPER_URL: str = "http://localhost:3009"
    SEARXNG_URL: str = "http://localhost:8888"
    KNOWLEDGE_DIR: str = "knowledge"
    HASH_CACHE_FILE: str = ".engine/data/knowledge_hashes.json"
    AGENCY_API_KEY: str = "agency-secret-key-phase1"


settings = MemorySettings()

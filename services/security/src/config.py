"""Configuration for Security Audit Gateway."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class SecuritySettings(BaseSettings):
    """Runtime settings loaded from environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    SECURITY_GATEWAY_PORT: int = 3015
    SONARQUBE_URL: str = "http://localhost:9000"
    SONARQUBE_TOKEN: str = "sqa_test_token"
    AGENCY_API_KEY: str = "agency-secret-key-phase1"
    GITLEAKS_BIN: str = "gitleaks"
    SEMGREP_BIN: str = "semgrep"
    TRIVY_BIN: str = "trivy"
    NUCLEI_BIN: str = "nuclei"


settings = SecuritySettings()

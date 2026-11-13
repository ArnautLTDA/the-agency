"""Configuration settings for Banco Inter Payment Gateway (:3006)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class PaymentSettings(BaseSettings):
    """Runtime configuration loaded from environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PAYMENT_PORT: int = 3006
    INTER_API_BASE: str = "https://cdpj-sandbox.inter.co"
    INTER_CLIENT_ID: str = "sandbox_inter_client_id"
    INTER_CLIENT_SECRET: str = "sandbox_inter_client_secret"
    INTER_CERT_PATH: str = "certs/inter/sandbox.crt"
    INTER_KEY_PATH: str = "certs/inter/sandbox.key"
    INTER_PIX_KEY: str = "sandbox_pix_key_agency@inter.co"
    INTER_WEBHOOK_KEY: str = "inter_webhook_secret_key_123"
    INTER_IP_WHITELIST: str = "54.232.0.0/16,54.207.0.0/16,127.0.0.1,testclient,::1"
    RABBITMQ_URL: str = "amqp://agency:agency123@localhost:5672/"
    DATABASE_PATH: str = "pipeline.db"
    AGENCY_API_KEY: str = "agency-secret-key-phase1"

    @property
    def ip_whitelist_set(self) -> set[str]:
        return {ip.strip() for ip in self.INTER_IP_WHITELIST.split(",") if ip.strip()}


settings = PaymentSettings()

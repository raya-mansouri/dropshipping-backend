"""
Application Settings
====================
Single source of truth for all environment-based configuration.
Read via get_settings() — never via os.getenv or
directly.
"""

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "postgres"
    db_password: SecretStr = SecretStr("")
    db_name: str = "basalam"

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = (
        ""  # Falls back to redis_url if empty (see workers/celery_config.py)
    )

    # ------------------------------------------------------------------
    # Kafka
    # ------------------------------------------------------------------
    kafka_bootstrap_servers: str = "localhost:9092"

    # ------------------------------------------------------------------
    # JWT / Auth (secret_key required)
    # ------------------------------------------------------------------
    secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # ------------------------------------------------------------------
    # Basalam API (client_id and client_secret required)
    # ------------------------------------------------------------------
    basalam_client_id: str = ""
    basalam_client_secret: SecretStr = SecretStr("")
    base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:3000"  # Used for OAuth redirect_uri
    docs_offline: bool = False
    basalam_auth_url: str = "https://auth.basalam.com"
    basalam_api_url: str = "https://openapi.basalam.com/v1"
    basalam_webhook_url: str = "https://webhook.basalam.com/v1"

    # ------------------------------------------------------------------
    # MinIO / Storage
    # ------------------------------------------------------------------
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: SecretStr = SecretStr("minioadmin")
    minio_bucket: str = "basalam-images"
    minio_region: str = "us-east-1"
    minio_use_ssl: bool = False

    # ------------------------------------------------------------------
    # Image Processing
    # ------------------------------------------------------------------
    cdn_base_url: str = "https://cdn.basalam.com"
    image_max_width: int = 1920
    image_max_height: int = 1920
    image_quality: int = 85
    image_format: str = "WEBP"
    image_http_timeout: float = 30.0

    # ------------------------------------------------------------------
    # Kavenegar SMS
    # ------------------------------------------------------------------
    kavenegar_api_key: str = ""
    kavenegar_sender: str = "10000000"

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    app_env: str = "production"
    log_level: str = "INFO"
    sentry_dsn: str = ""
    cors_origins: str = ""

    # ------------------------------------------------------------------
    # Payment Gateway
    # ------------------------------------------------------------------
    payment_gateway: Literal["zarinpal", "zibal"] = "zarinpal"
    payment_env: Literal["sandbox", "production"] = "sandbox"
    payment_callback_url: str = ""
    zarinpal_merchant_id: str = ""
    payment_fee_rate: Decimal = Decimal("0.03")  # 3% platform commission

    # ------------------------------------------------------------------
    # Webhook Security
    # ------------------------------------------------------------------
    webhook_base_url: str = (
        ""  # Base URL for webhook endpoint (e.g., https://api.example.com)
    )
    webhook_default_rate_limit: int = 100  # requests per minute
    webhook_default_timestamp_tolerance: int = 300  # seconds

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password.get_secret_value()}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings instance. Parsed once per process."""
    return Settings()

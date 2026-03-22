"""
Application Settings
====================
Single source of truth for all environment-based configuration.
Read via get_settings() — never via os.getenv or 
directly.
"""
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # Database 
    # ------------------------------------------------------------------
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/basalam"

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # ------------------------------------------------------------------
    # Kafka
    # ------------------------------------------------------------------
    kafka_bootstrap_servers: str = "localhost:9092"

    # ------------------------------------------------------------------
    # JWT / Auth (secret_key required)
    # ------------------------------------------------------------------
    secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ------------------------------------------------------------------
    # Basalam API (client_id and client_secret required)
    # ------------------------------------------------------------------
    basalam_client_id: str = ""
    basalam_client_secret: SecretStr = SecretStr("")
    base_url: str = "http://localhost:8000"

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
    # Application
    # ------------------------------------------------------------------
    app_env: str = "development"
    log_level: str = "INFO"
    sentry_dsn: str = ""
    cors_origins: str = "*"


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings instance. Parsed once per process."""
    return Settings()

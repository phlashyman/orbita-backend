"""
Orbita configuration — loaded from environment variables ONLY.
Uses pydantic-settings for type-safe config management.

NO HARDCODED SECRETS — all sensitive values come from environment variables.
On Railway, DATABASE_URL is auto-injected by the PostgreSQL service.
"""
import os
import secrets
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Orbita API"
    debug: bool = False

    # Database — auto-fixed for asyncpg on Railway
    database_url: str = ""

    @field_validator("database_url", mode="before")
    @classmethod
    def fix_asyncpg(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL is required — set it via environment variable")
        if "postgresql://" in v and "+asyncpg" not in v:
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # Security — generated at runtime if not provided (for dev only)
    secret_key: str = ""

    @field_validator("secret_key", mode="before")
    @classmethod
    def ensure_secret_key(cls, v: str) -> str:
        if not v:
            import warnings
            warnings.warn("SECRET_KEY not set — generating random key (NOT PERSISTENT). Set SECRET_KEY in production!")
            return secrets.token_urlsafe(32)
        if v == "orbita-super-secret-key-change-in-production":
            import warnings
            warnings.warn("Default SECRET_KEY detected! Set a strong random key in production.")
        return v

    access_token_expire_minutes: int = 60

    # AI
    anthropic_api_key: str = ""
    ai_daily_cap_usd: float = 5.0

    # SerpAPI
    serpapi_key: str = ""

    # S3 / Cloudflare R2
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "orbita-receipts"
    s3_region: str = "auto"

    # CORS
    cors_origins: str = ""

    # Railway / Production
    railway_environment: str = "development"

    # Sentry
    sentry_dsn: str = ""

    @property
    def database_url_sync(self) -> str:
        return self.database_url.replace("+asyncpg", "+psycopg2")

    @property
    def s3_config(self) -> dict:
        if not self.s3_endpoint:
            return {}
        return {
            "endpoint_url": self.s3_endpoint,
            "aws_access_key_id": self.s3_access_key,
            "aws_secret_access_key": self.s3_secret_key,
            "region_name": self.s3_region,
        }


settings = Settings()

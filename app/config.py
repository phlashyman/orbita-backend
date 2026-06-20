"""
Orbita configuration — loaded from environment variables.
Uses pydantic-settings for type-safe config management.

On Railway, DATABASE_URL is injected by PostgreSQL as:
  postgresql://user:pass@host:5432/railway
We auto-convert to asyncpg format:
  postgresql+asyncpg://user:pass@host:5432/railway
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Orbita API"
    debug: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://orbita:orbita_secret@localhost:5432/orbita"

    @field_validator("database_url", mode="before")
    @classmethod
    def fix_asyncpg(cls, v: str) -> str:
        """Auto-convert postgresql:// to postgresql+asyncpg:// for asyncpg driver."""
        if v and "postgresql://" in v and "+asyncpg" not in v:
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # Security
    secret_key: str = "orbita-super-secret-key-change-in-production"
    access_token_expire_minutes: int = 60

    # AI
    anthropic_api_key: str = ""
    ai_daily_cap_usd: float = 5.0

    # SerpAPI
    serpapi_key: str = ""

    # S3 / MinIO
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "orbita-receipts"
    s3_region: str = "us-east-1"

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Railway / Production
    railway_environment: str = ""

    # Sentry
    sentry_dsn: str = ""

    @property
    def database_url_sync(self) -> str:
        """Alembic requires a sync driver."""
        return self.database_url.replace("+asyncpg", "+psycopg2")

    @property
    def s3_config(self) -> dict:
        return {
            "endpoint_url": self.s3_endpoint,
            "aws_access_key_id": self.s3_access_key,
            "aws_secret_access_key": self.s3_secret_key,
            "region_name": self.s3_region,
        }


settings = Settings()

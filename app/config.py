"""
Orbita configuration — loaded from environment variables.
Uses pydantic-settings for type-safe config management.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Orbita API"
    debug: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://orbita:orbita_secret@localhost:5432/orbita"

    # Security
    secret_key: str = "orbita-super-secret-key-change-in-production"
    access_token_expire_minutes: int = 60

    # AI
    anthropic_api_key: str = ""

    # S3 / MinIO
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "orbita-receipts"
    s3_region: str = "us-east-1"

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

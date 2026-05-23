"""
Configuration management using pydantic-settings.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables with sensible defaults."""

    # Database
    DATABASE_URL: str = Field(
        default="sqlite:///./modeltrack.db",
        description="SQLAlchemy database URL",
    )

    # API Server
    API_HOST: str = Field(
        default="0.0.0.0",
        description="Host to bind API server to",
    )
    API_PORT: int = Field(
        default=8000,
        description="Port to bind API server to",
    )

    # Logging
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    # Storage
    MODELS_DIR: str = Field(
        default="./models_store",
        description="Directory to store model binaries",
    )
    PIPELINES_DIR: str = Field(
        default="./pipelines_store",
        description="Directory to store pipeline definitions",
    )

    # Optional overrides
    SECRET_KEY: Optional[str] = Field(
        default=None,
        description="Secret key for signing tokens",
    )
    DEBUG: bool = Field(
        default=False,
        description="Enable debug mode",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()

"""Application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    base_url: str = Field(validation_alias="BASE_URL")
    token: str = Field(validation_alias="TOKEN")
    logging_level: str = Field(
        default="INFO",
        description=(
            "Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL). "
            "Can be set via LOGGING_LEVEL environment variable or .env file"
        ),
        validation_alias="LOGGING_LEVEL",
    )
    logging_format: str = Field(
        default="standard",
        description=(
            "Logging format ('standard' or 'detailed'). "
            "Can be set via LOGGING_FORMAT environment variable or .env file"
        ),
        validation_alias="LOGGING_FORMAT",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()  # ty: ignore[missing-argument]

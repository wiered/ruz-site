"""Application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8-sig",
    )

    api_url: str = Field(validation_alias=AliasChoices("API_URL", "api_url"))
    api_key: str = Field(validation_alias=AliasChoices("API_KEY", "api_key"))
    telegram_bot_token: str = Field(
        validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "telegram_bot_token")
    )
    session_secret: str = Field(
        validation_alias=AliasChoices("SESSION_SECRET", "session_secret")
    )
    telegram_auth_max_age_seconds: int = Field(
        default=300,
        validation_alias=AliasChoices(
            "TELEGRAM_AUTH_MAX_AGE_SECONDS",
            "telegram_auth_max_age_seconds",
        ),
    )
    session_max_age_seconds: int = Field(
        default=604800,
        validation_alias=AliasChoices(
            "SESSION_MAX_AGE_SECONDS",
            "session_max_age_seconds",
        ),
    )
    cookie_secure: bool = Field(
        default=False,
        validation_alias=AliasChoices("COOKIE_SECURE", "cookie_secure"),
    )

    host: str = Field(
        default="127.0.0.1",
        description="Uvicorn host adress",
        validation_alias=AliasChoices("HOST", "host"),
    )
    port: int = Field(
        default=3000,
        description="Uvicorn host port",
        validation_alias=AliasChoices("PORT", "port"),
    )

    logging_level: str = Field(
        default="INFO",
        description=(
            "Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL). "
            "Can be set via LOGGING_LEVEL environment variable or .env file"
        ),
        validation_alias=AliasChoices("LOGGING_LEVEL", "logging_level"),
    )
    logging_format: str = Field(
        default="standard",
        description=(
            "Logging format ('standard' or 'detailed'). "
            "Can be set via LOGGING_FORMAT environment variable or .env file"
        ),
        validation_alias=AliasChoices("LOGGING_FORMAT", "logging_format"),
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()  # ty: ignore[missing-argument]

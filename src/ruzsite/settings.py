"""Application settings."""

from functools import lru_cache
import json
from pathlib import Path
from typing import Annotated, Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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
        default=True,
        validation_alias=AliasChoices("COOKIE_SECURE", "cookie_secure"),
    )
    trusted_proxy_ips: Annotated[tuple[str, ...], NoDecode] = Field(
        default=("127.0.0.1", "::1", "localhost", "testclient"),
        validation_alias=AliasChoices("TRUSTED_PROXY_IPS", "trusted_proxy_ips"),
    )
    allowed_hosts: Annotated[tuple[str, ...], NoDecode] = Field(
        default=("127.0.0.1", "localhost", "testserver"),
        validation_alias=AliasChoices("ALLOWED_HOSTS", "allowed_hosts"),
    )
    redis_url: str = Field(
        default="redis://127.0.0.1:6379/0",
        validation_alias=AliasChoices("REDIS_URL", "redis_url"),
    )
    auth_ip_rate_limit: int = Field(
        default=10,
        validation_alias=AliasChoices("AUTH_IP_RATE_LIMIT", "auth_ip_rate_limit"),
    )
    auth_ip_rate_window_seconds: int = Field(
        default=60,
        validation_alias=AliasChoices(
            "AUTH_IP_RATE_WINDOW_SECONDS",
            "auth_ip_rate_window_seconds",
        ),
    )
    auth_user_rate_limit: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "AUTH_USER_RATE_LIMIT",
            "auth_user_rate_limit",
        ),
    )
    auth_user_rate_window_seconds: int = Field(
        default=3600,
        validation_alias=AliasChoices(
            "AUTH_USER_RATE_WINDOW_SECONDS",
            "auth_user_rate_window_seconds",
        ),
    )
    schedule_cache_ttl_seconds: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "SCHEDULE_CACHE_TTL_SECONDS",
            "schedule_cache_ttl_seconds",
        ),
    )
    schedule_user_rate_limit: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "SCHEDULE_USER_RATE_LIMIT",
            "schedule_user_rate_limit",
        ),
    )
    schedule_user_rate_window_seconds: int = Field(
        default=60,
        validation_alias=AliasChoices(
            "SCHEDULE_USER_RATE_WINDOW_SECONDS",
            "schedule_user_rate_window_seconds",
        ),
    )
    schedule_ip_rate_limit: int = Field(
        default=120,
        validation_alias=AliasChoices(
            "SCHEDULE_IP_RATE_LIMIT",
            "schedule_ip_rate_limit",
        ),
    )
    schedule_ip_rate_window_seconds: int = Field(
        default=60,
        validation_alias=AliasChoices(
            "SCHEDULE_IP_RATE_WINDOW_SECONDS",
            "schedule_ip_rate_window_seconds",
        ),
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

    @field_validator("trusted_proxy_ips", "allowed_hosts", mode="before")
    @classmethod
    def _parse_multi_value_strings(cls, value: Any) -> Any:
        """Accept JSON arrays or comma-separated env vars for string tuples."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return ()
            if stripped.startswith("["):
                return tuple(json.loads(stripped))
            return tuple(item.strip() for item in stripped.split(",") if item.strip())
        return value


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()  # ty: ignore[missing-argument]

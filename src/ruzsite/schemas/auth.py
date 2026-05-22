"""Authentication schemas."""

from pydantic import BaseModel, ConfigDict, Field


class TelegramAuthRequest(BaseModel):
    """Telegram auth request payload."""

    init_data: str | None = Field(default=None, alias="initData")

    model_config = ConfigDict(populate_by_name=True)


class TelegramUser(BaseModel):
    """Telegram user extracted from signed Mini App init data."""

    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    is_premium: bool | None = None


class SessionData(BaseModel):
    """Signed session payload."""

    telegram_user_id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    issued_at: int

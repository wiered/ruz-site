"""Homepage schemas."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ruzsite.schemas.auth import TelegramUser


@dataclass(slots=True)
class HomepageState:
    """Homepage rendering state."""

    authenticated: bool
    telegram_user: TelegramUser | None
    ruz_user: Mapping[str, object] | None
    error_message: str | None = None

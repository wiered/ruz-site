"""Tests for Telegram Mini App authentication."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from asyncio import run
from collections.abc import Mapping
from urllib.parse import urlencode

import pytest
from starlette.requests import Request

os.environ["API_URL"] = "https://example.com"
os.environ["API_KEY"] = "test-api-key"
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:telegram-test-token"
os.environ["SESSION_SECRET"] = "test-session-secret"

import ruzsite.app as app_module
from fastapi import HTTPException
from ruzsite.schemas.auth import SessionData
from ruzsite.schemas.homepage import HomepageState
from ruzsite.settings import get_settings
from ruzsite.services.auth_service import (
    SESSION_COOKIE_NAME,
    decode_session,
    encode_session,
    verify_telegram_init_data,
)
from ruzsite.services import homepage_service


def _build_init_data(*, bot_token: str, user: dict[str, object], auth_date: int) -> str:
    """Build a signed Telegram Mini App init data string for tests."""
    fields = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    data_check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(fields.items(), key=lambda item: item[0])
    )
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    fields["hash"] = hmac.new(
        secret,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(fields)


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    """Reset cached settings between tests."""
    get_settings.cache_clear()


def test_verify_telegram_auth_accepts_valid_payload() -> None:
    """Telegram auth verification should accept a valid Mini App payload."""
    settings = get_settings()
    init_data = _build_init_data(
        bot_token=settings.telegram_bot_token,
        user={"id": 424242, "first_name": "Ruz", "username": "ruz_user"},
        auth_date=int(time.time()),
    )

    user = verify_telegram_init_data(
        init_data,
        bot_token=settings.telegram_bot_token,
        max_age_seconds=settings.telegram_auth_max_age_seconds,
    )

    assert user.id == 424242
    assert user.username == "ruz_user"


def test_telegram_auth_rejects_tampered_payload() -> None:
    """Telegram auth should reject invalid signatures."""
    settings = get_settings()
    init_data = _build_init_data(
        bot_token=settings.telegram_bot_token,
        user={"id": 1, "first_name": "Alice"},
        auth_date=int(time.time()),
    )
    tampered = init_data.replace("Alice", "Mallory")

    with pytest.raises(HTTPException) as exc_info:
        verify_telegram_init_data(
            tampered,
            bot_token=settings.telegram_bot_token,
            max_age_seconds=settings.telegram_auth_max_age_seconds,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Telegram initData signature is invalid."


def test_signed_session_round_trip() -> None:
    """Signed session cookies should decode back to the original payload."""
    settings = get_settings()
    session = SessionData(
        telegram_user_id=555,
        first_name="Captain",
        username="captain",
        issued_at=int(time.time()),
    )

    encoded = encode_session(session, secret=settings.session_secret)
    decoded = decode_session(
        encoded,
        secret=settings.session_secret,
        max_age_seconds=settings.session_max_age_seconds,
    )

    assert decoded == session


def test_homepage_shows_basic_user_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """Homepage should render Telegram and Ruz user data for a valid session."""

    async def fake_load_ruz_user(user_id: int) -> Mapping[str, object]:
        assert user_id == 555
        return {
            "id": 555,
            "username": "captain",
            "group_oid": 99,
            "subgroup": 1,
        }

    monkeypatch.setattr(homepage_service, "load_ruz_user", fake_load_ruz_user)
    settings = get_settings()
    session = SessionData(
        telegram_user_id=555,
        first_name="Captain",
        username="captain",
        issued_at=int(time.time()),
    )
    cookie = encode_session(session, secret=settings.session_secret)
    request = Request(
        {
            "type": "http",
            "headers": [(b"cookie", f"{SESSION_COOKIE_NAME}={cookie}".encode("utf-8"))],
        }
    )

    state = run(homepage_service.session_state(request))
    assert isinstance(state, HomepageState)

    page = homepage_service.build_page(state)

    assert "Captain" in page
    assert "captain" in page
    assert "99" in page

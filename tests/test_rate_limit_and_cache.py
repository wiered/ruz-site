"""Tests for Redis-backed rate limits and schedule cache."""

from __future__ import annotations

from asyncio import run
import hashlib
import hmac
import json
import os
import time
from typing import Any
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

os.environ["API_URL"] = "https://example.com"
os.environ["API_KEY"] = "test-api-key"
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:telegram-test-token"
os.environ["SESSION_SECRET"] = "test-session-secret"

import ruzsite.app as app_module
from ruzsite.schemas.auth import SessionData
from ruzsite.services.auth_service import SESSION_COOKIE_NAME, encode_session
from ruzsite.services import rate_limit_service, schedule_service
from ruzsite.settings import get_settings


class FakeRedis:
    """Minimal async Redis double for rate limit and cache tests."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, name: str) -> int:
        """Increment an integer counter."""
        value = self.counters.get(name, 0) + 1
        self.counters[name] = value
        return value

    async def expire(self, name: str, time: int) -> bool:
        """Assign a TTL to a key."""
        self.ttls[name] = time
        return True

    async def ttl(self, name: str) -> int:
        """Return a configured TTL for a key."""
        return self.ttls.get(name, -1)

    async def get(self, name: str) -> str | None:
        """Return a cached string value."""
        return self.values.get(name)

    async def set(self, name: str, value: str, ex: int | None = None) -> bool:
        """Store a cached string value."""
        self.values[name] = value
        if ex is not None:
            self.ttls[name] = ex
        return True


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


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    """Replace the shared Redis client with an in-memory fake."""
    redis = FakeRedis()

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(rate_limit_service, "_redis", fake_get_redis)
    return redis


def test_auth_ip_rate_limit_blocks_eleventh_request(fake_redis: FakeRedis) -> None:
    """Telegram auth should reject the eleventh request from one IP."""
    settings = get_settings()
    init_data = _build_init_data(
        bot_token=settings.telegram_bot_token,
        user={"id": 777, "first_name": "Ruz"},
        auth_date=int(time.time()),
    )
    client = TestClient(app_module.app)

    for _ in range(10):
        response = client.post(
            "/auth/telegram",
            json={"initData": init_data},
            headers={
                "Origin": "http://testserver",
                "X-Forwarded-For": "203.0.113.10",
            },
        )
        assert response.status_code == 200

    blocked = client.post(
        "/auth/telegram",
        json={"initData": init_data},
        headers={
            "Origin": "http://testserver",
            "X-Forwarded-For": "203.0.113.10",
        },
    )

    assert blocked.status_code == 429
    assert (
        blocked.json()["detail"]
        == "Too many Telegram auth attempts from this IP address."
    )
    assert blocked.headers["Retry-After"] == "60"


def test_auth_user_rate_limit_blocks_thirty_first_request(
    fake_redis: FakeRedis,
) -> None:
    """Telegram auth should reject the thirty-first request for one Telegram user."""
    settings = get_settings()
    client = TestClient(app_module.app)

    for index in range(30):
        init_data = _build_init_data(
            bot_token=settings.telegram_bot_token,
            user={"id": 888, "first_name": "Ruz"},
            auth_date=int(time.time()),
        )
        response = client.post(
            "/auth/telegram",
            json={"initData": init_data},
            headers={
                "Origin": "http://testserver",
                "X-Forwarded-For": f"203.0.113.{index}",
            },
        )
        assert response.status_code == 200

    init_data = _build_init_data(
        bot_token=settings.telegram_bot_token,
        user={"id": 888, "first_name": "Ruz"},
        auth_date=int(time.time()),
    )
    blocked = client.post(
        "/auth/telegram",
        json={"initData": init_data},
        headers={
            "Origin": "http://testserver",
            "X-Forwarded-For": "198.51.100.50",
        },
    )

    assert blocked.status_code == 429
    assert (
        blocked.json()["detail"]
        == "Too many Telegram auth attempts for this Telegram user."
    )
    assert blocked.headers["Retry-After"] == "3600"


def test_auth_rejects_cross_origin_request(fake_redis: FakeRedis) -> None:
    """Telegram auth should reject cross-site requests before verification."""
    settings = get_settings()
    init_data = _build_init_data(
        bot_token=settings.telegram_bot_token,
        user={"id": 777, "first_name": "Ruz"},
        auth_date=int(time.time()),
    )
    client = TestClient(app_module.app)

    response = client.post(
        "/auth/telegram",
        json={"initData": init_data},
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Telegram auth request origin is invalid."


def test_auth_accepts_forwarded_https_origin(fake_redis: FakeRedis) -> None:
    """Telegram auth should accept the public HTTPS origin behind a proxy."""
    settings = get_settings()
    init_data = _build_init_data(
        bot_token=settings.telegram_bot_token,
        user={"id": 777, "first_name": "Ruz"},
        auth_date=int(time.time()),
    )
    client = TestClient(app_module.app)

    response = client.post(
        "/auth/telegram",
        json={"initData": init_data},
        headers={
            "Origin": "https://ruz.example",
            "X-Forwarded-Host": "ruz.example",
            "X-Forwarded-Proto": "https",
        },
    )

    assert response.status_code == 200


def test_auth_rejects_non_json_request(fake_redis: FakeRedis) -> None:
    """Telegram auth should only accept JSON bodies."""
    settings = get_settings()
    init_data = _build_init_data(
        bot_token=settings.telegram_bot_token,
        user={"id": 777, "first_name": "Ruz"},
        auth_date=int(time.time()),
    )
    client = TestClient(app_module.app)

    response = client.post(
        "/auth/telegram",
        content=init_data,
        headers={
            "Origin": "http://testserver",
            "Content-Type": "text/plain",
        },
    )

    assert response.status_code == 415
    assert (
        response.json()["detail"]
        == "Telegram auth endpoint only accepts JSON requests."
    )


def test_get_client_ip_ignores_forwarded_for_from_untrusted_client() -> None:
    """Forwarded headers should be ignored unless the direct peer is trusted."""
    request = Request(
        {
            "type": "http",
            "headers": [(b"x-forwarded-for", b"203.0.113.10")],
            "client": ("198.51.100.7", 54321),
        }
    )

    assert rate_limit_service.get_client_ip(request) == "198.51.100.7"


def test_schedule_state_uses_cached_schedule_after_first_request(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schedule requests should reuse Redis cache before hitting the Ruz API again."""
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
            "client": ("127.0.0.1", 12345),
        }
    )
    load_calls: list[int] = []
    schedule_payload: list[dict[str, Any]] = [
        {
            "lesson_id": 1,
            "date": "2026-05-22",
            "begin_lesson": "08:30:00",
            "end_lesson": "10:00:00",
            "sub_group": 1,
            "discipline_name": "Math",
            "kind_of_work": "Лекции",
            "lecturer_short_name": "Dr. A",
            "lecturer_id": 1,
            "discipline_id": 11,
            "auditorium_name": "101",
            "building": "A",
            "group_id": 100,
        }
    ]

    async def fake_load_user_schedule(user_id: int) -> list[dict[str, Any]]:
        load_calls.append(user_id)
        return schedule_payload

    monkeypatch.setattr(schedule_service, "load_user_schedule", fake_load_user_schedule)

    first_state = run(schedule_service.schedule_state(request))
    second_state = run(schedule_service.schedule_state(request))

    assert (
        first_state.schedule_rows[0].cells["08:30:00-10:00:00"][0].discipline_name
        == "Math"
    )
    assert (
        second_state.schedule_rows[0].cells["08:30:00-10:00:00"][0].discipline_name
        == "Math"
    )
    assert load_calls == [555]
    assert fake_redis.ttls["cache:schedule:555"] == settings.schedule_cache_ttl_seconds

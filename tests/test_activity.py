"""Tests for activity throttling, concurrent updates and request authentication."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from importlib import import_module

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from starlette.requests import Request

os.environ["API_URL"] = "https://example.com"
os.environ["API_KEY"] = "test-api-key"
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:telegram-test-token"
os.environ["SESSION_SECRET"] = "test-session-secret"

from ruzsite.schemas.auth import SessionData
from ruzsite.services import activity_service
from ruzsite.services.auth_service import SESSION_COOKIE_NAME, encode_session
from ruzsite.settings import get_settings


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch):
    """Provide an offline API and Redis with atomic per-user lock acquisition."""
    redis = AsyncMock()
    values: dict[str, str] = {}
    held: set[str] = set()

    async def get(name):
        return values.get(name)

    async def set_value(name, value, *, ex):
        values[name] = value
        return True

    def make_lock(name, **kwargs):
        lock = AsyncMock()

        async def acquire():
            if name in held:
                return False
            held.add(name)
            return True

        async def release():
            held.remove(name)

        lock.acquire.side_effect = acquire
        lock.release.side_effect = release
        return lock

    redis.get.side_effect = get
    redis.set.side_effect = set_value
    redis.lock = make_lock
    client = AsyncMock()
    client.users.get_by_id.return_value = {"last_used_at": None}
    client.users.touch.return_value = True
    client.__aenter__.return_value = client
    monkeypatch.setattr(activity_service, "get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(activity_service, "RuzClient", lambda **kwargs: client)
    return redis, client


@pytest.mark.parametrize("age", [None, 300, 600])
def test_missing_or_old_activity_is_touched_once(backend, age) -> None:
    """Repeated actions within the cooldown must produce only one PUT."""
    redis, client = backend
    if age is not None:
        client.users.get_by_id.return_value = {
            "last_used_at": (datetime.now(UTC) - timedelta(seconds=age)).isoformat()
        }

    async def scenario():
        await activity_service.touch_user_activity(42)
        await activity_service.touch_user_activity(42)

    asyncio.run(scenario())
    client.users.get_by_id.assert_awaited_once_with(user_id=42)
    client.users.touch.assert_awaited_once_with(user_id=42)
    redis.set.assert_awaited_once_with("activity:cooldown:42", "1", ex=300)


@pytest.mark.parametrize("naive", [False, True])
def test_recent_activity_from_bot_is_respected(backend, naive) -> None:
    """Recent UTC timestamps from either client prevent another PUT."""
    redis, client = backend
    timestamp = datetime.now(UTC) - timedelta(seconds=60)
    if naive:
        timestamp = timestamp.replace(tzinfo=None)
    client.users.get_by_id.return_value = {"last_used_at": timestamp.isoformat()}
    asyncio.run(activity_service.touch_user_activity(42))
    client.users.touch.assert_not_awaited()
    assert 239 <= redis.set.await_args.kwargs["ex"] <= 240


def test_concurrent_actions_do_not_duplicate_touch(backend) -> None:
    """A request already updating one user excludes concurrent requests."""
    _, client = backend

    async def fetch(**kwargs):
        await asyncio.sleep(0)
        return {"last_used_at": None}

    client.users.get_by_id.side_effect = fetch

    async def scenario():
        await asyncio.gather(
            *(activity_service.touch_user_activity(42) for _ in range(8))
        )

    asyncio.run(scenario())
    client.users.touch.assert_awaited_once()


@pytest.mark.parametrize("failure", [False, RuntimeError("API offline")])
def test_failed_touch_can_be_retried(backend, failure) -> None:
    """False responses and exceptions must not start a successful cooldown."""
    _, client = backend
    client.users.touch.side_effect = [failure, True]

    async def scenario():
        await activity_service.touch_user_activity(42)
        await activity_service.touch_user_activity(42)

    asyncio.run(scenario())
    assert client.users.touch.await_count == 2


def test_redis_failure_is_suppressed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Analytics storage failure must not escape the background task."""
    monkeypatch.setattr(
        activity_service,
        "get_redis",
        AsyncMock(side_effect=RuntimeError("Redis offline")),
    )
    asyncio.run(activity_service.touch_user_activity(42))


@pytest.mark.parametrize("cookie_kind", ["missing", "invalid", "expired", "valid"])
def test_only_verified_sessions_queue_activity(cookie_kind) -> None:
    """Anonymous, forged and expired sessions must never report activity."""
    settings = get_settings()
    cookie = ""
    if cookie_kind == "invalid":
        cookie = f"{SESSION_COOKIE_NAME}=invalid"
    elif cookie_kind in {"expired", "valid"}:
        issued_at = int(time.time())
        if cookie_kind == "expired":
            issued_at -= settings.session_max_age_seconds + 1
        session = SessionData(
            telegram_user_id=42, first_name="Test", issued_at=issued_at
        )
        cookie = f"{SESSION_COOKIE_NAME}={encode_session(session, secret=settings.session_secret)}"
    request = Request({"type": "http", "headers": [(b"cookie", cookie.encode())]})
    tasks = BackgroundTasks()
    activity_service.queue_request_activity(request, tasks)
    assert len(tasks.tasks) == (1 if cookie_kind == "valid" else 0)
    if tasks.tasks:
        assert tasks.tasks[0].args == (42,)


@pytest.mark.parametrize(
    ("path", "module", "state_function"),
    [
        ("/", "homepage", "session_state"),
        ("/schedule", "schedule", "schedule_state"),
        ("/settings?q=test", "settings", "settings_state"),
    ],
)
def test_page_requests_run_background_activity(
    backend, monkeypatch: pytest.MonkeyPatch, path, module, state_function
) -> None:
    """Each authenticated page must actually execute its queued activity task."""
    from ruzsite.app import app

    route = import_module(f"ruzsite.routes.{module}")
    monkeypatch.setattr(route, state_function, AsyncMock(return_value=None))
    monkeypatch.setattr(route, "build_page", lambda state: "Page")
    settings = get_settings()
    session = SessionData(
        telegram_user_id=42, first_name="Test", issued_at=int(time.time())
    )
    client = TestClient(app)
    client.cookies.set(
        SESSION_COOKIE_NAME, encode_session(session, secret=settings.session_secret)
    )
    response = client.get(path)
    assert response.status_code == 200
    assert response.text == "Page"
    backend[1].users.touch.assert_awaited_once_with(user_id=42)


def test_authenticated_crawler_request_does_not_report_activity(backend) -> None:
    """Non-user routes must be excluded even when a session cookie is present."""
    from ruzsite.app import app

    settings = get_settings()
    session = SessionData(
        telegram_user_id=42, first_name="Test", issued_at=int(time.time())
    )
    client = TestClient(app)
    client.cookies.set(
        SESSION_COOKIE_NAME, encode_session(session, secret=settings.session_secret)
    )
    assert client.get("/robots.txt").status_code == 200
    backend[1].users.get_by_id.assert_not_awaited()

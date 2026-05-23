"""Tests for the settings page."""

from __future__ import annotations

from asyncio import run
from contextlib import asynccontextmanager
import os
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from ruzclient import UNSET
from starlette.requests import Request

os.environ["API_URL"] = "https://example.com"
os.environ["API_KEY"] = "test-api-key"
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:telegram-test-token"
os.environ["SESSION_SECRET"] = "test-session-secret"

import ruzsite.app as app_module
from ruzsite.schemas.auth import SessionData
from ruzsite.schemas.settings import SettingsPageState
from ruzsite.services import rate_limit_service, settings_service
from ruzsite.services.auth_service import SESSION_COOKIE_NAME, encode_session
from ruzsite.settings import get_settings


class FakeGroupsApi:
    """Minimal fake groups API for settings tests."""

    def __init__(
        self,
        *,
        search_results: list[dict[str, Any]] | None = None,
        group_by_oid: dict[int, dict[str, Any]] | None = None,
    ) -> None:
        self.search_results = [] if search_results is None else search_results
        self.group_by_oid = {} if group_by_oid is None else group_by_oid
        self.search_queries: list[str] = []

    async def search_groups_by_name(self, query: str) -> list[dict[str, Any]]:
        """Return configured search hits."""
        self.search_queries.append(query)
        return self.search_results

    async def get_group(self, group_oid: int) -> dict[str, Any]:
        """Return a configured group or simulate a missing one."""
        if group_oid not in self.group_by_oid:
            raise ValueError(f"Group with id {group_oid} not found")
        return self.group_by_oid[group_oid]


class FakeUsersApi:
    """Minimal fake users API for settings tests."""

    def __init__(self, *, existing_user: dict[str, Any] | None = None) -> None:
        self.existing_user = existing_user
        self.created_payloads: list[Any] = []
        self.updated_payloads: list[tuple[int, Any]] = []

    async def get_by_id(self, user_id: int) -> dict[str, Any]:
        """Return a configured existing user or simulate a missing user."""
        if self.existing_user is None:
            from ruzclient.errors import RuzHttpError

            raise RuzHttpError(
                status_code=404,
                message="user not found",
                method="GET",
                url=f"https://example.com/api/user/{user_id}",
            )
        return self.existing_user

    async def create_user(self, payload: Any) -> dict[str, Any]:
        """Record create payloads."""
        self.created_payloads.append(payload)
        return {
            "id": payload.id,
            "group_oid": payload.group_oid,
            "subgroup": payload.subgroup,
            "username": payload.username,
            "created_at": "2026-05-23T00:00:00Z",
            "last_used_at": "2026-05-23T00:00:00Z",
        }

    async def update_user(self, user_id: int, payload: Any) -> dict[str, Any]:
        """Record update payloads."""
        self.updated_payloads.append((user_id, payload))
        return {
            "id": user_id,
            "group_oid": payload.group_oid,
            "subgroup": None,
            "username": "captain",
            "created_at": "2026-05-23T00:00:00Z",
            "last_used_at": "2026-05-23T00:00:00Z",
        }


class FakeRuzClient:
    """Container for fake groups and users APIs."""

    def __init__(self, *, groups: FakeGroupsApi, users: FakeUsersApi) -> None:
        self.groups = groups
        self.users = users


class FakeRedis:
    """Minimal async Redis double for settings rate limit tests."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
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


def _build_request() -> Request:
    """Create a request with a valid signed session cookie."""
    settings = get_settings()
    session = SessionData(
        telegram_user_id=555,
        first_name="Captain",
        username="captain",
        issued_at=int(time.time()),
    )
    cookie = encode_session(session, secret=settings.session_secret)
    return Request(
        {
            "type": "http",
            "headers": [(b"cookie", f"{SESSION_COOKIE_NAME}={cookie}".encode("utf-8"))],
        }
    )


def test_settings_page_redirects_without_session() -> None:
    """Anonymous users should be redirected away from settings."""
    client = TestClient(app_module.app)

    response = client.get("/settings", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/"


def test_settings_state_loads_current_group_and_search_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings search should include current group data and matching results."""
    request = _build_request()
    fake_client = FakeRuzClient(
        groups=FakeGroupsApi(
            search_results=[
                {
                    "oid": 321,
                    "name": "AB-123",
                    "guid": "guid-321",
                    "faculty_name": "Flight Ops",
                }
            ]
        ),
        users=FakeUsersApi(),
    )

    async def fake_load_ruz_user(user_id: int) -> dict[str, Any]:
        assert user_id == 555
        return {
            "group_oid": 111,
            "group_name": "OLD-111",
            "subgroup": 2,
        }

    @asynccontextmanager
    async def fake_ruz_client():
        yield fake_client

    monkeypatch.setattr(settings_service, "load_ruz_user", fake_load_ruz_user)
    monkeypatch.setattr(settings_service, "_ruz_client", fake_ruz_client)

    state = run(settings_service.settings_state(request, group_query="AB-123"))

    assert isinstance(state, SettingsPageState)
    assert state.current_group_oid == 111
    assert state.current_group_name == "OLD-111"
    assert state.current_subgroup == 2
    assert state.group_query == "AB-123"
    assert len(state.group_results) == 1
    assert state.group_results[0].oid == 321
    assert fake_client.groups.search_queries == ["AB-123"]


def test_settings_state_resolves_current_group_name_via_group_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings should fetch the current group name when the user payload lacks it."""
    request = _build_request()
    fake_client = FakeRuzClient(
        groups=FakeGroupsApi(
            group_by_oid={
                918: {
                    "id": 918,
                    "guid": "guid-918",
                    "name": "ИБАС-42",
                    "faculty_name": "Flight Ops",
                }
            }
        ),
        users=FakeUsersApi(),
    )

    async def fake_load_ruz_user(user_id: int) -> dict[str, Any]:
        assert user_id == 555
        return {
            "group_oid": 918,
            "subgroup": 1,
        }

    @asynccontextmanager
    async def fake_ruz_client():
        yield fake_client

    monkeypatch.setattr(settings_service, "load_ruz_user", fake_load_ruz_user)
    monkeypatch.setattr(settings_service, "_ruz_client", fake_ruz_client)

    state = run(settings_service.settings_state(request))

    assert state.current_group_oid == 918
    assert state.current_group_name == "ИБАС-42"
    assert state.current_subgroup == 1


def test_change_group_creates_missing_user_and_clears_schedule_cache(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing group should create a user when none exists yet."""
    request = _build_request()
    fake_users = FakeUsersApi(existing_user=None)
    fake_client = FakeRuzClient(
        groups=FakeGroupsApi(
            group_by_oid={
                321: {
                    "id": 321,
                    "guid": "guid-321",
                    "name": "AB-123",
                    "faculty_name": "Flight Ops",
                }
            }
        ),
        users=fake_users,
    )
    load_calls = [
        {"group_oid": 111, "group_name": "OLD-111", "subgroup": 2},
        {"group_oid": 321, "group_name": "AB-123", "subgroup": 2},
    ]
    invalidated_users: list[int] = []

    async def fake_load_ruz_user(user_id: int) -> dict[str, Any]:
        assert user_id == 555
        return load_calls.pop(0)

    async def fake_invalidate_cached_schedule(user_id: int) -> None:
        invalidated_users.append(user_id)

    @asynccontextmanager
    async def fake_ruz_client():
        yield fake_client

    monkeypatch.setattr(settings_service, "load_ruz_user", fake_load_ruz_user)
    monkeypatch.setattr(
        settings_service,
        "invalidate_cached_schedule",
        fake_invalidate_cached_schedule,
    )
    monkeypatch.setattr(settings_service, "_ruz_client", fake_ruz_client)

    state = run(
        settings_service.change_group(
            request,
            group_oid=321,
            group_label="AB-123",
        )
    )

    assert state.success_message == "Group updated successfully."
    assert state.current_group_oid == 321
    assert len(fake_users.created_payloads) == 1
    payload = fake_users.created_payloads[0]
    assert payload.id == 555
    assert payload.username == "captain"
    assert payload.group_oid == 321
    assert payload.subgroup is None
    assert payload.group_guid == "guid-321"
    assert payload.group_name == "AB-123"
    assert invalidated_users == [555]


def test_change_group_updates_existing_user_without_resetting_subgroup(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing group for an existing user should use partial update semantics."""
    request = _build_request()
    fake_users = FakeUsersApi(
        existing_user={
            "id": 555,
            "group_oid": 111,
            "subgroup": 2,
            "username": "captain",
            "created_at": "2026-05-23T00:00:00Z",
            "last_used_at": "2026-05-23T00:00:00Z",
        }
    )
    fake_client = FakeRuzClient(
        groups=FakeGroupsApi(group_by_oid={}),
        users=fake_users,
    )
    load_calls = [
        {"group_oid": 111, "group_name": "OLD-111", "subgroup": 2},
        {"group_oid": 321, "group_name": "AB-123", "subgroup": 2},
    ]

    async def fake_load_ruz_user(user_id: int) -> dict[str, Any]:
        assert user_id == 555
        return load_calls.pop(0)

    async def fake_invalidate_cached_schedule(user_id: int) -> None:
        assert user_id == 555

    @asynccontextmanager
    async def fake_ruz_client():
        fake_client.groups.search_results = [
            {
                "oid": 321,
                "name": "AB-123",
                "guid": "guid-321",
                "faculty_name": "Flight Ops",
            }
        ]
        yield fake_client

    monkeypatch.setattr(settings_service, "load_ruz_user", fake_load_ruz_user)
    monkeypatch.setattr(
        settings_service,
        "invalidate_cached_schedule",
        fake_invalidate_cached_schedule,
    )
    monkeypatch.setattr(settings_service, "_ruz_client", fake_ruz_client)

    state = run(
        settings_service.change_group(
            request,
            group_oid=321,
            group_label="AB-123",
        )
    )

    assert state.success_message == "Group updated successfully."
    assert fake_client.groups.search_queries == ["AB-123"]
    assert fake_users.created_payloads == []
    assert len(fake_users.updated_payloads) == 1
    updated_user_id, payload = fake_users.updated_payloads[0]
    assert updated_user_id == 555
    assert payload.group_oid == 321
    assert payload.group_guid == "guid-321"
    assert payload.group_name == "AB-123"
    assert payload.faculty_name == "Flight Ops"
    assert payload.subgroup is UNSET


def test_change_subgroup_updates_existing_user_and_clears_schedule_cache(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing subgroup should send a partial update with only subgroup."""
    request = _build_request()
    fake_users = FakeUsersApi(
        existing_user={
            "id": 555,
            "group_oid": 918,
            "subgroup": 1,
            "username": "captain",
            "created_at": "2026-05-23T00:00:00Z",
            "last_used_at": "2026-05-23T00:00:00Z",
        }
    )
    fake_client = FakeRuzClient(
        groups=FakeGroupsApi(),
        users=fake_users,
    )
    load_calls = [
        {"group_oid": 918, "group_name": "ИБАС-42", "subgroup": 1},
        {"group_oid": 918, "group_name": "ИБАС-42", "subgroup": 2},
    ]
    invalidated_users: list[int] = []

    async def fake_load_ruz_user(user_id: int) -> dict[str, Any]:
        assert user_id == 555
        return load_calls.pop(0)

    async def fake_invalidate_cached_schedule(user_id: int) -> None:
        invalidated_users.append(user_id)

    @asynccontextmanager
    async def fake_ruz_client():
        yield fake_client

    monkeypatch.setattr(settings_service, "load_ruz_user", fake_load_ruz_user)
    monkeypatch.setattr(
        settings_service,
        "invalidate_cached_schedule",
        fake_invalidate_cached_schedule,
    )
    monkeypatch.setattr(settings_service, "_ruz_client", fake_ruz_client)

    state = run(settings_service.change_subgroup(request, subgroup=2))

    assert state.success_message == "Subgroup updated successfully."
    assert state.current_subgroup == 2
    assert invalidated_users == [555]
    assert len(fake_users.updated_payloads) == 1
    updated_user_id, payload = fake_users.updated_payloads[0]
    assert updated_user_id == 555
    assert payload.subgroup == 2
    assert payload.group_oid is UNSET
    assert payload.group_guid is UNSET
    assert payload.group_name is UNSET


def test_settings_page_renders_group_search_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The settings page should render the new group search and selection UI."""
    fake_client = FakeRuzClient(
        groups=FakeGroupsApi(
            search_results=[
                {
                    "oid": 321,
                    "name": "AB-123",
                    "guid": "guid-321",
                    "faculty_name": "Flight Ops",
                }
            ]
        ),
        users=FakeUsersApi(),
    )

    async def fake_load_ruz_user(user_id: int) -> dict[str, Any]:
        assert user_id == 555
        return {
            "group_oid": 111,
            "group_name": "OLD-111",
            "subgroup": 2,
        }

    @asynccontextmanager
    async def fake_ruz_client():
        yield fake_client

    monkeypatch.setattr(settings_service, "load_ruz_user", fake_load_ruz_user)
    monkeypatch.setattr(settings_service, "_ruz_client", fake_ruz_client)

    settings = get_settings()
    session = SessionData(
        telegram_user_id=555,
        first_name="Captain",
        username="captain",
        issued_at=int(time.time()),
    )
    cookie = encode_session(session, secret=settings.session_secret)
    client = TestClient(app_module.app)
    client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = client.get("/settings?q=AB-123", follow_redirects=False)

    assert response.status_code == 200
    assert "Preferences for this device" in response.text
    assert "OLD-111" in response.text
    assert "Find a new group" in response.text
    assert 'data-theme-choice="system"' in response.text
    assert 'action="/settings/group"' in response.text
    assert 'action="/settings/subgroup"' in response.text
    assert 'value="0"' in response.text
    assert 'value="1"' in response.text
    assert 'value="2"' in response.text
    assert "AB-123" in response.text


def test_group_change_rate_limit_blocks_eleventh_request(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Group updates should reject the eleventh request for one Telegram user."""
    fake_users = FakeUsersApi(
        existing_user={
            "id": 555,
            "group_oid": 111,
            "subgroup": 2,
            "username": "captain",
            "created_at": "2026-05-23T00:00:00Z",
            "last_used_at": "2026-05-23T00:00:00Z",
        }
    )
    fake_client = FakeRuzClient(
        groups=FakeGroupsApi(
            group_by_oid={
                321: {
                    "id": 321,
                    "guid": "guid-321",
                    "name": "AB-123",
                    "faculty_name": "Flight Ops",
                }
            }
        ),
        users=fake_users,
    )

    async def fake_load_ruz_user(user_id: int) -> dict[str, Any]:
        assert user_id == 555
        return {"group_oid": 321, "group_name": "AB-123", "subgroup": 2}

    async def fake_invalidate_cached_schedule(user_id: int) -> None:
        assert user_id == 555

    @asynccontextmanager
    async def fake_ruz_client():
        yield fake_client

    monkeypatch.setattr(settings_service, "load_ruz_user", fake_load_ruz_user)
    monkeypatch.setattr(
        settings_service,
        "invalidate_cached_schedule",
        fake_invalidate_cached_schedule,
    )
    monkeypatch.setattr(settings_service, "_ruz_client", fake_ruz_client)

    settings = get_settings()
    session = SessionData(
        telegram_user_id=555,
        first_name="Captain",
        username="captain",
        issued_at=int(time.time()),
    )
    cookie = encode_session(session, secret=settings.session_secret)
    client = TestClient(app_module.app)
    client.cookies.set(SESSION_COOKIE_NAME, cookie)

    for _ in range(10):
        response = client.post(
            "/settings/group",
            data={"group_oid": "321", "group_label": "AB-123"},
            follow_redirects=False,
        )
        assert response.status_code == 200

    blocked = client.post(
        "/settings/group",
        data={"group_oid": "321", "group_label": "AB-123"},
        follow_redirects=False,
    )

    assert blocked.status_code == 429
    assert (
        blocked.json()["detail"]
        == "Too many group change attempts for this Telegram user."
    )
    assert blocked.headers["Retry-After"] == "60"


def test_subgroup_change_rate_limit_blocks_eleventh_request(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Subgroup updates should reject the eleventh request for one Telegram user."""
    fake_users = FakeUsersApi(
        existing_user={
            "id": 555,
            "group_oid": 918,
            "subgroup": 1,
            "username": "captain",
            "created_at": "2026-05-23T00:00:00Z",
            "last_used_at": "2026-05-23T00:00:00Z",
        }
    )
    fake_client = FakeRuzClient(
        groups=FakeGroupsApi(),
        users=fake_users,
    )

    async def fake_load_ruz_user(user_id: int) -> dict[str, Any]:
        assert user_id == 555
        return {"group_oid": 918, "group_name": "ИБАС-42", "subgroup": 2}

    async def fake_invalidate_cached_schedule(user_id: int) -> None:
        assert user_id == 555

    @asynccontextmanager
    async def fake_ruz_client():
        yield fake_client

    monkeypatch.setattr(settings_service, "load_ruz_user", fake_load_ruz_user)
    monkeypatch.setattr(
        settings_service,
        "invalidate_cached_schedule",
        fake_invalidate_cached_schedule,
    )
    monkeypatch.setattr(settings_service, "_ruz_client", fake_ruz_client)

    settings = get_settings()
    session = SessionData(
        telegram_user_id=555,
        first_name="Captain",
        username="captain",
        issued_at=int(time.time()),
    )
    cookie = encode_session(session, secret=settings.session_secret)
    client = TestClient(app_module.app)
    client.cookies.set(SESSION_COOKIE_NAME, cookie)

    for _ in range(10):
        response = client.post(
            "/settings/subgroup",
            data={"subgroup": "2"},
            follow_redirects=False,
        )
        assert response.status_code == 200

    blocked = client.post(
        "/settings/subgroup",
        data={"subgroup": "2"},
        follow_redirects=False,
    )

    assert blocked.status_code == 429
    assert (
        blocked.json()["detail"]
        == "Too many subgroup change attempts for this Telegram user."
    )
    assert blocked.headers["Retry-After"] == "60"

"""Shared isolation for optional activity reporting in request tests."""

from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError


@pytest.fixture(autouse=True)
def isolate_activity_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent background analytics from contacting real services in unit tests."""
    from ruzsite.services import activity_service

    monkeypatch.setattr(
        activity_service,
        "get_redis",
        AsyncMock(side_effect=RedisConnectionError("Activity Redis is not configured")),
    )

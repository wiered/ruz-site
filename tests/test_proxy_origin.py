"""Tests for proxy-aware request origin validation."""

import os

import pytest
from starlette.requests import Request

os.environ["API_URL"] = "https://example.com"
os.environ["API_KEY"] = "test-api-key"
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:telegram-test-token"
os.environ["SESSION_SECRET"] = "test-session-secret"

from ruzsite.services.auth_service import validate_same_origin
from ruzsite.settings import get_settings


def test_validate_same_origin_accepts_proxy_from_configured_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A proxy inside a configured CIDR should supply the public origin."""
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1,172.18.0.0/16")
    get_settings.cache_clear()
    request = Request(
        {
            "type": "http",
            "scheme": "http",
            "server": ("ruz.wiered.ru", 80),
            "client": ("172.18.0.14", 12345),
            "path": "/auth/telegram",
            "headers": [
                (b"host", b"ruz.wiered.ru"),
                (b"origin", b"https://ruz.wiered.ru"),
                (b"x-forwarded-host", b"ruz.wiered.ru"),
                (b"x-forwarded-proto", b"https"),
            ],
        }
    )

    validate_same_origin(request)

"""Tests for proxy-aware request metadata."""

import os

import pytest
from starlette.requests import Request

os.environ["API_URL"] = "https://example.com"
os.environ["API_KEY"] = "test-api-key"
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:telegram-test-token"
os.environ["SESSION_SECRET"] = "test-session-secret"

from ruzsite.services.request_metadata_service import (
    get_effective_client_ip,
    get_uvicorn_forwarded_allow_ips,
)
from ruzsite.settings import get_settings


def test_get_effective_client_ip_trusts_forwarded_for_from_configured_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trusted proxy networks should expose the forwarded client IP."""
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1,172.18.0.0/16")
    get_settings.cache_clear()
    request = Request(
        {
            "type": "http",
            "scheme": "https",
            "server": ("ruz.example", 443),
            "client": ("172.18.0.14", 12345),
            "path": "/",
            "headers": [
                (b"host", b"ruz.example"),
                (b"x-forwarded-for", b"198.51.100.25, 172.18.0.14"),
            ],
        }
    )

    assert get_effective_client_ip(request) == "198.51.100.25"


def test_uvicorn_forwarded_allow_ips_uses_configured_networks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uvicorn should trust configured IP addresses and networks."""
    monkeypatch.setenv(
        "TRUSTED_PROXY_IPS",
        "127.0.0.1,localhost,172.18.0.0/16",
    )
    get_settings.cache_clear()

    assert get_uvicorn_forwarded_allow_ips() == "127.0.0.1,172.18.0.0/16"

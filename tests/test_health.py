"""Tests for the health endpoint."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

os.environ["API_URL"] = "https://example.com"
os.environ["API_KEY"] = "test-api-key"
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:telegram-test-token"
os.environ["SESSION_SECRET"] = "test-session-secret"

import ruzsite.app as app_module


def test_health_returns_ok_status() -> None:
    """Health endpoint should respond with a stable OK payload."""
    client = TestClient(app_module.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

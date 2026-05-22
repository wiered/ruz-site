"""Redis-backed rate limiting and schedule cache helpers."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Protocol, cast

from fastapi import HTTPException, Request, status
from ruzclient.http.endpoints.schedule import UserScheduleLesson

from ruzsite.logging_config import setup_logging
from ruzsite.schemas.rate_limit import RateLimitResult
from ruzsite.services.redis_service import get_redis
from ruzsite.settings import get_settings

setup_logging()
logger = logging.getLogger(__name__)


class RedisProtocol(Protocol):
    """Minimal Redis protocol used by this service."""

    async def incr(self, name: str) -> int:
        """Increment a numeric key and return the new value."""

    async def expire(self, name: str, time: int) -> bool:
        """Set a key expiration in seconds."""

    async def ttl(self, name: str) -> int:
        """Return the remaining TTL for a key."""

    async def get(self, name: str) -> str | None:
        """Get a cached string value by key."""

    async def set(self, name: str, value: str, ex: int | None = None) -> bool | None:
        """Set a cached string value with an optional expiration."""


def get_client_ip(request: Request) -> str:
    """Return the best-effort client IP for the request."""
    settings = get_settings()
    client_host = request.client.host if request.client else None
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for and client_host in settings.trusted_proxy_ips:
        return forwarded_for.split(",", maxsplit=1)[0].strip()
    if client_host:
        return client_host
    return "unknown"


async def _redis() -> RedisProtocol:
    """Return the configured Redis client."""
    return cast(RedisProtocol, await get_redis())


def _rate_limit_key(scope: str, subject: str) -> str:
    """Build a stable Redis key for a rate limit scope."""
    return f"rl:{scope}:{subject}"


def _schedule_cache_key(telegram_user_id: int) -> str:
    """Build a stable Redis key for cached schedule data."""
    return f"cache:schedule:{telegram_user_id}"


async def check_rate_limit(
    *,
    scope: str,
    subject: str,
    limit: int,
    window_seconds: int,
) -> RateLimitResult:
    """Check and update a Redis-backed fixed-window rate limit."""
    redis = await _redis()
    key = _rate_limit_key(scope, subject)
    current = await redis.incr(key)
    if current == 1:
        await redis.expire(key, window_seconds)

    ttl_seconds = await redis.ttl(key)
    retry_after_seconds = window_seconds if ttl_seconds < 0 else ttl_seconds
    remaining = max(limit - current, 0)
    allowed = current <= limit
    logger.debug(
        "Rate limit scope=%s subject=%s current=%s limit=%s ttl=%s allowed=%s",
        scope,
        subject,
        current,
        limit,
        retry_after_seconds,
        allowed,
    )
    return RateLimitResult(
        allowed=allowed,
        limit=limit,
        remaining=remaining,
        retry_after_seconds=retry_after_seconds,
    )


async def enforce_rate_limit(
    *,
    scope: str,
    subject: str,
    limit: int,
    window_seconds: int,
    detail: str,
) -> None:
    """Raise HTTP 429 when the rate limit is exceeded."""
    result = await check_rate_limit(
        scope=scope,
        subject=subject,
        limit=limit,
        window_seconds=window_seconds,
    )
    if result.allowed:
        return

    logger.warning(
        "Rate limit exceeded scope=%s subject=%s retry_after_seconds=%s",
        scope,
        subject,
        result.retry_after_seconds,
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(result.retry_after_seconds)},
    )


async def get_cached_schedule(telegram_user_id: int) -> list[UserScheduleLesson] | None:
    """Load a cached schedule snapshot for a Telegram user."""
    redis = await _redis()
    payload = await redis.get(_schedule_cache_key(telegram_user_id))
    if payload is None:
        return None
    logger.debug("Loaded cached schedule for Telegram user ID %s", telegram_user_id)
    return json.loads(payload)


async def cache_schedule(
    telegram_user_id: int,
    schedule: Sequence[UserScheduleLesson],
    *,
    ttl_seconds: int,
) -> None:
    """Store a serialized schedule snapshot for a Telegram user."""
    redis = await _redis()
    await redis.set(
        _schedule_cache_key(telegram_user_id),
        json.dumps(list(schedule), ensure_ascii=False, separators=(",", ":")),
        ex=ttl_seconds,
    )
    logger.debug(
        "Cached schedule for Telegram user ID %s ttl_seconds=%s",
        telegram_user_id,
        ttl_seconds,
    )

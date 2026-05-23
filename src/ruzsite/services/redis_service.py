"""Redis client lifecycle helpers."""

from __future__ import annotations

import logging
from inspect import isawaitable

from redis.asyncio import Redis
from redis.exceptions import RedisError

from ruzsite.logging_config import setup_logging
from ruzsite.settings import get_settings

setup_logging()
logger = logging.getLogger(__name__)
_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """Return a shared Redis client instance."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        logger.info("Initialized Redis client")
    return _redis_client


async def ensure_redis_available() -> None:
    """Verify Redis connectivity and raise a readable startup error if unavailable."""
    settings = get_settings()
    redis = await get_redis()
    try:
        ping_result = redis.ping()
        if isawaitable(ping_result):
            await ping_result
    except RedisError as exc:
        message = (
            "Redis is required for rate limiting and schedule caching, but the "
            f"application could not connect to {settings.redis_url}. "
            "Check REDIS_URL and make sure Redis is running before starting the app."
        )
        logger.error(message)
        raise RuntimeError(message) from exc


async def close_redis() -> None:
    """Close the shared Redis client if it was initialized."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Closed Redis client")

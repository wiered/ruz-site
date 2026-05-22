"""Redis client lifecycle helpers."""

from __future__ import annotations

import logging

from redis.asyncio import Redis

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


async def close_redis() -> None:
    """Close the shared Redis client if it was initialized."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Closed Redis client")

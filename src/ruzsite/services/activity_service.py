"""Best-effort user activity reporting to the RUZ backend."""

from __future__ import annotations

import logging
from asyncio import timeout
from datetime import UTC, datetime
from math import ceil

from fastapi import BackgroundTasks, HTTPException, Request
from ruzclient import ClientConfig, RuzClient

from ruzsite.services.auth_service import SESSION_COOKIE_NAME, decode_session
from ruzsite.services.redis_service import get_redis
from ruzsite.settings import get_settings

logger = logging.getLogger(__name__)
ACTIVITY_INTERVAL_SECONDS = 300


def queue_request_activity(request: Request, background_tasks: BackgroundTasks) -> None:
    """Queue activity only for requests with a verified authenticated session."""
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        return
    settings = get_settings()
    try:
        session = decode_session(
            cookie,
            secret=settings.session_secret,
            max_age_seconds=settings.session_max_age_seconds,
        )
    except (HTTPException, ValueError):
        return
    background_tasks.add_task(touch_user_activity, session.telegram_user_id)


def _remaining_interval(last_used_at: str | None) -> int:
    """Return the cooldown in seconds, treating naive API timestamps as UTC."""
    if not last_used_at:
        return 0
    last_used = datetime.fromisoformat(last_used_at)
    if last_used.tzinfo is None:
        last_used = last_used.replace(tzinfo=UTC)
    elapsed = (datetime.now(UTC) - last_used).total_seconds()
    return max(0, ceil(ACTIVITY_INTERVAL_SECONDS - elapsed))


async def touch_user_activity(user_id: int) -> None:
    """Report activity at most every five minutes across all site workers."""
    try:
        # Bound activity work; cleanup has its own budget after cancellation.
        async with timeout(10):
            redis = await get_redis()
            cooldown_key = f"activity:cooldown:{user_id}"
            lock = redis.lock(f"activity:lock:{user_id}", timeout=15, blocking=False)
            if not await lock.acquire():
                return
            try:
                if await redis.get(cooldown_key):
                    return
                settings = get_settings()
                config = ClientConfig(
                    base_url=settings.api_url, api_key=settings.api_key
                )
                async with RuzClient(config=config) as client:
                    user = await client.users.get_by_id(user_id=user_id)
                    remaining = _remaining_interval(user.get("last_used_at"))
                    if remaining:
                        await redis.set(cooldown_key, "1", ex=remaining)
                    elif await client.users.touch(user_id=user_id):
                        await redis.set(cooldown_key, "1", ex=ACTIVITY_INTERVAL_SECONDS)
            finally:
                try:
                    async with timeout(1):
                        await lock.release()
                except TimeoutError:
                    # The 15-second lock TTL also handles unavailable Redis.
                    logger.warning(
                        "Timed out releasing activity lock for user ID %s", user_id
                    )
    except Exception:
        # Analytics must never break navigation, settings, or authentication.
        logger.warning(
            "Failed to report activity for user ID %s", user_id, exc_info=True
        )

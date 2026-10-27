"""Regression coverage for lock cleanup after the activity deadline expires."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from ruzsite.services import activity_service


def test_activity_deadline_also_bounds_stalled_lock_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A timed-out Redis read followed by a stalled release must still finish."""
    real_timeout = asyncio.timeout
    monkeypatch.setattr(activity_service, "timeout", lambda seconds: real_timeout(0.02))

    async def scenario() -> None:
        never = asyncio.Event()
        release_started = asyncio.Event()
        release_cancelled = asyncio.Event()
        lock = AsyncMock()
        lock.acquire.return_value = True

        async def blocked_read(name: str) -> None:
            await never.wait()

        async def blocked_release() -> None:
            release_started.set()
            try:
                await never.wait()
            finally:
                release_cancelled.set()

        lock.release.side_effect = blocked_release
        redis = AsyncMock()
        redis.lock = lambda *args, **kwargs: lock
        redis.get.side_effect = blocked_read
        monkeypatch.setattr(
            activity_service, "get_redis", AsyncMock(return_value=redis)
        )

        task = asyncio.create_task(activity_service.touch_user_activity(42))
        try:
            # wait() leaves a hung task untouched, so the watchdog cannot hide
            # the bug by cancelling release() on behalf of production code.
            done, _ = await asyncio.wait({task}, timeout=1)
            assert release_started.is_set(), (
                "The activity deadline did not trigger cleanup"
            )
            assert task in done, (
                "Lock release outlived the activity and cleanup deadlines"
            )
            assert task.result() is None
            assert release_cancelled.is_set()
            lock.release.assert_awaited_once()
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())

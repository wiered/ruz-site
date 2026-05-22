"""Schemas for rate limiting and cache metadata."""

from pydantic import BaseModel


class RateLimitResult(BaseModel):
    """Result of a fixed-window rate limit check."""

    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int

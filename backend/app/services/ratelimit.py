"""Rate limiting: fixed-window counters (Redis in prod, memory in dev/tests)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int = 0


class RateLimiter(Protocol):
    async def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult: ...


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}

    async def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = time.time()
        cutoff = now - window_seconds
        hits = [t for t in self._hits.get(key, []) if t > cutoff]
        if len(hits) >= limit:
            retry_after = max(1, int(hits[0] + window_seconds - now))
            self._hits[key] = hits
            return RateLimitResult(allowed=False, retry_after_seconds=retry_after)
        hits.append(now)
        self._hits[key] = hits
        return RateLimitResult(allowed=True)


class RedisRateLimiter:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        redis_key = f"rl:{key}"
        count = await self._client.incr(redis_key)
        if count == 1:
            await self._client.expire(redis_key, window_seconds)
        if count > limit:
            ttl = await self._client.ttl(redis_key)
            return RateLimitResult(allowed=False, retry_after_seconds=max(1, int(ttl)))
        return RateLimitResult(allowed=True)


_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is not None:
        return _rate_limiter
    from app.config import get_settings
    from app.deps import get_redis_client

    settings = get_settings()
    if settings.uses_redis:
        _rate_limiter = RedisRateLimiter(get_redis_client())
    else:
        _rate_limiter = MemoryRateLimiter()
    return _rate_limiter


def reset_rate_limiter() -> None:
    global _rate_limiter
    _rate_limiter = None

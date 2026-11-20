"""Shared FastAPI dependencies and process-wide clients."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis

from app.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]

_redis: Redis | None = None


def get_redis_client() -> Redis:
    """Process-wide async Redis client (only call when settings.uses_redis)."""
    global _redis
    if _redis is None:
        settings = get_settings()
        if not settings.redis_url:
            raise RuntimeError("Redis is not configured (redis_url is empty).")
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis_client() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


async def enforce_rate_limit(limiter, key: str, limit: int, window_seconds: int) -> None:  # type: ignore[no-untyped-def]
    """Raise 429 + Retry-After when the fixed-window budget is exhausted."""
    from app.errors import AppError

    result = await limiter.check(key, limit, window_seconds)
    if not result.allowed:
        raise AppError(
            "rate_limited", "Too many requests. Please slow down.", 429, retryable=True,
            headers={"Retry-After": str(result.retry_after_seconds)},
        )


def get_mailer_dep() -> object:
    from app.services.mail import get_mailer

    return get_mailer()


def get_storage_dep() -> object:
    from app.services.storage import get_storage

    return get_storage()


def get_otp_store_dep() -> object:
    from app.services.otp_store import get_otp_store

    return get_otp_store()


def get_rate_limiter_dep() -> object:
    from app.services.ratelimit import get_rate_limiter

    return get_rate_limiter()


def get_job_runner_dep() -> object:
    from app.services.jobs import get_job_runner

    return get_job_runner()

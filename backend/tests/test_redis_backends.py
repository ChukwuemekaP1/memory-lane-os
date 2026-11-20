"""Redis-backed service tests (needs_redis; CI provides the server)."""

import asyncio
import os
import uuid

import pytest
from redis.asyncio import Redis

from app.services.otp_store import OtpRecord, RedisOtpStore
from app.services.ratelimit import RedisRateLimiter

pytestmark = pytest.mark.needs_redis


@pytest.fixture
async def redis_client():
    url = os.environ.get("REDIS_URL", "")
    if not url:
        pytest.skip("REDIS_URL is not set")
    client = Redis.from_url(url, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        pytest.skip("Redis unreachable")
    yield client
    await client.aclose()


def _unique(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex}"


async def test_redis_otp_store_roundtrip(redis_client):
    store = RedisOtpStore(redis_client)
    magic = _unique("magic")
    record = OtpRecord(email="r@x.com", code_hash="c", magic_hash=magic, attempts=0,
                       expires_at=0)
    await store.save(record, 60)
    loaded = await store.load_by_magic(magic)
    assert loaded is not None and loaded.email == "r@x.com"
    assert (await store.load_by_email("R@X.com")).magic_hash == magic
    assert await store.bump_attempts(magic) == 1
    await store.consume(magic)
    assert await store.load_by_magic(magic) is None


async def test_redis_otp_store_missing_key(redis_client):
    store = RedisOtpStore(redis_client)
    assert await store.load_by_magic(_unique("nope")) is None
    assert await store.bump_attempts(_unique("nope")) is None
    await store.consume(_unique("nope"))  # no error


async def test_redis_otp_store_expiry(redis_client):
    store = RedisOtpStore(redis_client)
    magic = _unique("short")
    record = OtpRecord(email="e@x.com", code_hash="c", magic_hash=magic, attempts=0,
                       expires_at=0)
    await store.save(record, 1)
    await asyncio.sleep(2)
    assert await store.load_by_magic(magic) is None


async def test_redis_rate_limiter_window(redis_client):
    limiter = RedisRateLimiter(redis_client)
    key = _unique("rl")
    assert (await limiter.check(key, 2, 60)).allowed
    assert (await limiter.check(key, 2, 60)).allowed
    denied = await limiter.check(key, 2, 60)
    assert not denied.allowed
    assert denied.retry_after_seconds >= 1
    assert (await limiter.check(_unique("rl"), 2, 60)).allowed

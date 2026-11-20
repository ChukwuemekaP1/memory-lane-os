"""OTP/magic-challenge hot store (Redis in prod, memory in dev/tests).

The DB `otp_challenges` table is the audit trail; this store is the hot path
for verify/consume/attempt-counting with TTL expiry.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Protocol

from redis.asyncio import Redis


@dataclass
class OtpRecord:
    email: str
    code_hash: str
    magic_hash: str
    attempts: int
    expires_at: float  # unix timestamp


class OtpStore(Protocol):
    async def save(self, record: OtpRecord, ttl_seconds: int) -> None: ...
    async def load_by_magic(self, magic_hash: str) -> OtpRecord | None: ...
    async def load_by_email(self, email: str) -> OtpRecord | None: ...
    async def bump_attempts(self, magic_hash: str) -> int | None:
        """Increment attempts; returns new count, or None if missing/expired."""
        ...
    async def consume(self, magic_hash: str) -> None: ...


class MemoryOtpStore:
    def __init__(self) -> None:
        self._by_magic: dict[str, OtpRecord] = {}
        self._by_email: dict[str, str] = {}  # email -> magic_hash

    async def save(self, record: OtpRecord, ttl_seconds: int) -> None:
        record.expires_at = time.time() + ttl_seconds
        self._by_magic[record.magic_hash] = record
        self._by_email[record.email.lower()] = record.magic_hash

    def _get(self, magic_hash: str) -> OtpRecord | None:
        record = self._by_magic.get(magic_hash)
        if record is None:
            return None
        if record.expires_at <= time.time():
            self._by_magic.pop(magic_hash, None)
            return None
        return record

    async def load_by_magic(self, magic_hash: str) -> OtpRecord | None:
        return self._get(magic_hash)

    async def load_by_email(self, email: str) -> OtpRecord | None:
        magic_hash = self._by_email.get(email.lower())
        if magic_hash is None:
            return None
        return self._get(magic_hash)

    async def bump_attempts(self, magic_hash: str) -> int | None:
        record = self._get(magic_hash)
        if record is None:
            return None
        record.attempts += 1
        return record.attempts

    async def consume(self, magic_hash: str) -> None:
        record = self._by_magic.pop(magic_hash, None)
        if record is not None:
            self._by_email.pop(record.email.lower(), None)


class RedisOtpStore:
    def __init__(self, client: Redis) -> None:
        self._client = client

    @staticmethod
    def _magic_key(magic_hash: str) -> str:
        return f"otp:magic:{magic_hash}"

    @staticmethod
    def _email_key(email: str) -> str:
        return f"otp:email:{email.lower()}"

    async def save(self, record: OtpRecord, ttl_seconds: int) -> None:
        record.expires_at = time.time() + ttl_seconds
        body = json.dumps(asdict(record))
        async with self._client.pipeline() as pipe:
            pipe.set(self._magic_key(record.magic_hash), body, ex=ttl_seconds)
            pipe.set(self._email_key(record.email), record.magic_hash, ex=ttl_seconds)
            await pipe.execute()

    async def load_by_magic(self, magic_hash: str) -> OtpRecord | None:
        raw = await self._client.get(self._magic_key(magic_hash))
        if raw is None:
            return None
        data = json.loads(raw)
        if data["expires_at"] <= time.time():
            return None
        return OtpRecord(**data)

    async def load_by_email(self, email: str) -> OtpRecord | None:
        magic_hash = await self._client.get(self._email_key(email))
        if magic_hash is None:
            return None
        if isinstance(magic_hash, bytes):
            magic_hash = magic_hash.decode()
        return await self.load_by_magic(magic_hash)

    async def bump_attempts(self, magic_hash: str) -> int | None:
        record = await self.load_by_magic(magic_hash)
        if record is None:
            return None
        record.attempts += 1
        ttl = max(1, int(record.expires_at - time.time()))
        await self._client.set(self._magic_key(magic_hash), json.dumps(asdict(record)), ex=ttl)
        return record.attempts

    async def consume(self, magic_hash: str) -> None:
        record = await self.load_by_magic(magic_hash)
        keys = [self._magic_key(magic_hash)]
        if record is not None:
            keys.append(self._email_key(record.email))
        await self._client.delete(*keys)


_otp_store: OtpStore | None = None


def get_otp_store() -> OtpStore:
    global _otp_store
    if _otp_store is not None:
        return _otp_store
    from app.config import get_settings
    from app.deps import get_redis_client

    settings = get_settings()
    _otp_store = RedisOtpStore(get_redis_client()) if settings.uses_redis else MemoryOtpStore()
    return _otp_store


def reset_otp_store() -> None:
    global _otp_store
    _otp_store = None

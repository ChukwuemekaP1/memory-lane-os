"""Pure-Python UUIDv7 generator (RFC 9562).

PostgreSQL 16 has no uuidv7() builtin, so ids are generated app-side. This
also lets handlers return the id before insert (useful for idempotency).
"""

from __future__ import annotations

import secrets
import time
import uuid


def uuid7() -> uuid.UUID:
    unix_ms = time.time_ns() // 1_000_000
    rand = secrets.token_bytes(10)
    raw = bytearray(16)
    raw[0:6] = unix_ms.to_bytes(6, "big")
    raw[6:16] = rand
    raw[6] = (raw[6] & 0x0F) | 0x70  # version 7
    raw[8] = (raw[8] & 0x3F) | 0x80  # variant 10
    return uuid.UUID(bytes=bytes(raw))

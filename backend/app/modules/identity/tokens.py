"""Pure token helpers for passwordless auth (no I/O; fully unit-testable)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from uuid import UUID

CODE_LENGTH = 6
MAGIC_TOKEN_BYTES = 32
REFRESH_SECRET_BYTES = 32


def generate_code() -> str:
    """Six-digit OTP code (may start with 0)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def generate_magic_token() -> str:
    return secrets.token_hex(MAGIC_TOKEN_BYTES)


def generate_refresh_secret() -> str:
    return secrets.token_hex(REFRESH_SECRET_BYTES)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def secrets_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def mask_email(email: str) -> str:
    """o***@example.com — safe to return in API responses."""
    local, _, domain = email.partition("@")
    if not domain or not local:
        return "***"
    return f"{local[0]}***@{domain}"


@dataclass(frozen=True)
class ParsedSessionCookie:
    session_id: UUID
    refresh_secret: str


def parse_session_cookie(value: str) -> ParsedSessionCookie | None:
    """Parse `<session_id_hex>.<refresh_secret_hex>`. None when malformed."""
    session_hex, sep, secret = value.partition(".")
    if not sep or not session_hex or not secret:
        return None
    try:
        session_id = UUID(hex=session_hex)
    except ValueError:
        return None
    if len(secret) != REFRESH_SECRET_BYTES * 2:
        return None
    return ParsedSessionCookie(session_id=session_id, refresh_secret=secret)


def build_session_cookie(session_id: UUID, refresh_secret: str) -> str:
    return f"{session_id.hex}.{refresh_secret}"

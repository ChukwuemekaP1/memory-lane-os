"""Sync unit tests: UUIDv7 generator, error envelope, pagination, config."""

import uuid

import pytest

from app.errors import AppError, error_payload, ok_payload
from app.models.uuid7 import uuid7
from app.pagination import Cursor, normalize_limit


def test_uuid7_version_variant_and_uniqueness():
    ids = [uuid7() for _ in range(100)]
    assert len(set(ids)) == 100
    for value in ids:
        assert value.version == 7
        assert value.variant == uuid.RFC_4122


def test_uuid7_time_ordered():
    first, second = uuid7(), uuid7()
    assert first.bytes[:6] <= second.bytes[:6]


def test_error_payload_shape():
    payload = error_payload(AppError("gone", "Expired.", 410, details={"a": 1}))
    assert payload["error"]["code"] == "gone"
    assert payload["error"]["message"] == "Expired."
    assert payload["error"]["retryable"] is False
    assert payload["error"]["details"] == {"a": 1}
    assert "request_id" in payload["error"]


def test_ok_payload_shape():
    assert ok_payload({"x": 1})["data"] == {"x": 1}
    assert "request_id" in ok_payload(None)


def test_cursor_roundtrip_and_invalid():
    from datetime import datetime, timezone

    cursor = Cursor(created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    id=uuid.UUID("10000000-0000-0000-0000-000000000001"))
    decoded = Cursor.decode(cursor.encode())
    assert decoded == cursor
    with pytest.raises(AppError):
        Cursor.decode("not-a-cursor!!")


def test_normalize_limit_bounds():
    assert normalize_limit(None) == 20
    assert normalize_limit(50) == 50
    with pytest.raises(AppError):
        normalize_limit(0)
    with pytest.raises(AppError):
        normalize_limit(101)


def test_settings_reject_bad_db_scheme(monkeypatch):
    from pydantic import ValidationError

    from app.config import Settings

    monkeypatch.setenv("DATABASE_URL", "mysql://x")
    with pytest.raises(ValidationError):
        Settings()


def test_settings_require_secure_cookie_in_prod(monkeypatch):
    from pydantic import ValidationError

    from app.config import Settings

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    with pytest.raises(ValidationError):
        Settings()


def test_split_ssl_neon_style_urls():
    from app.db import _connect_args, _split_ssl

    clean, use_ssl = _split_ssl(
        "postgresql+asyncpg://u:p@ep-xyz.neon.tech/db?sslmode=require")
    assert use_ssl is True
    assert "sslmode" not in clean
    assert clean.startswith("postgresql+asyncpg://u:p@ep-xyz.neon.tech/db")
    args = _connect_args("postgresql+asyncpg://u:p@h/db?ssl=require")
    assert args == {"statement_cache_size": 0, "ssl": True}
    plain = _connect_args("postgresql+asyncpg://u:p@h/db")
    assert plain == {"statement_cache_size": 0}
    assert _connect_args("sqlite+aiosqlite:///x.db") == {"check_same_thread": False}

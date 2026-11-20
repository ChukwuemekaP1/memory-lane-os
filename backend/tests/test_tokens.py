"""Sync unit tests: auth token helpers (no I/O, run everywhere)."""

import re
from uuid import UUID

from app.modules.identity import tokens


def test_generate_code_format_and_uniqueness():
    codes = {tokens.generate_code() for _ in range(200)}
    assert len(codes) > 190  # overwhelmingly unique
    assert all(re.fullmatch(r"\d{6}", code) for code in codes)


def test_generate_magic_and_refresh_lengths():
    assert len(tokens.generate_magic_token()) == tokens.MAGIC_TOKEN_BYTES * 2
    assert len(tokens.generate_refresh_secret()) == tokens.REFRESH_SECRET_BYTES * 2
    assert tokens.generate_magic_token() != tokens.generate_magic_token()


def test_sha256_and_compare_digest():
    digest = tokens.sha256_hex("secret")
    assert len(digest) == 64
    assert tokens.secrets_equal(digest, tokens.sha256_hex("secret"))
    assert not tokens.secrets_equal(digest, tokens.sha256_hex("other"))


def test_normalize_and_mask_email():
    assert tokens.normalize_email("  Ada@Example.COM ") == "ada@example.com"
    assert tokens.mask_email("ada@example.com") == "a***@example.com"
    assert tokens.mask_email("not-an-email") == "***"


def test_session_cookie_roundtrip():
    session_id = UUID("10000000-0000-0000-0000-000000000001")
    secret = "ab" * tokens.REFRESH_SECRET_BYTES
    parsed = tokens.parse_session_cookie(tokens.build_session_cookie(session_id, secret))
    assert parsed is not None
    assert parsed.session_id == session_id
    assert parsed.refresh_secret == secret


def test_session_cookie_malformed():
    assert tokens.parse_session_cookie("") is None
    assert tokens.parse_session_cookie("no-separator") is None
    assert tokens.parse_session_cookie("not-a-uuid." + "ab" * 32) is None
    assert tokens.parse_session_cookie(f"{'00' * 16}.short") is None
    assert tokens.parse_session_cookie(f"{'00' * 16}.") is None

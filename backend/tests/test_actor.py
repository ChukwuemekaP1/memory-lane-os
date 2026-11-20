"""Guest actor resolution edge cases (needs_pg; PERMISSIONS_MATRIX Section 7)."""

from datetime import datetime, timedelta, timezone

import pytest
from starlette.requests import Request

from app.errors import AppError
from app.models.enums import GuestRoleCap
from app.models.spaces import GuestAccessToken
from app.modules.identity import tokens as token_helpers
from app.modules.permissions.actor import GuestActor, require_actor, resolve_actor

pytestmark = pytest.mark.needs_pg


def _request_with_token(raw: str) -> Request:
    return Request({
        "type": "http", "method": "GET", "path": "/", "scheme": "http",
        "server": ("test", 80), "headers": [(b"authorization", f"Bearer {raw}".encode())],
        "query_string": b"",
    })


async def _mint(session, space_row, label="T", role_cap=GuestRoleCap.contributor,
                raw="aa" * 32, **overrides):
    token = GuestAccessToken(space_id=space_row.id, token_hash=token_helpers.sha256_hex(raw),
                             label=label, role_cap=role_cap, use_count=0, **overrides)
    session.add(token)
    await session.flush()
    return token, raw


async def test_valid_token_resolves_and_counts_use(session, space_row):
    token, raw = await _mint(session, space_row)
    actor = await require_actor(_request_with_token(raw), session)
    assert isinstance(actor, GuestActor)
    assert actor.space_id == space_row.id
    assert actor.role_cap == GuestRoleCap.contributor
    await session.refresh(token)
    assert token.use_count == 1


async def test_revoked_token_gone(session, space_row):
    _, raw = await _mint(session, space_row, revoked_at=datetime.now(timezone.utc))
    with pytest.raises(AppError) as exc:
        await require_actor(_request_with_token(raw), session)
    assert exc.value.code == "gone"
    assert await resolve_actor(_request_with_token(raw), session) is None


async def test_expired_token_gone(session, space_row):
    _, raw = await _mint(session, space_row,
                          expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    with pytest.raises(AppError) as exc:
        await require_actor(_request_with_token(raw), session)
    assert exc.value.code == "gone"


async def test_max_uses_enforced(session, space_row):
    _, raw = await _mint(session, space_row, max_uses=1)
    first = await require_actor(_request_with_token(raw), session)
    assert isinstance(first, GuestActor)
    with pytest.raises(AppError) as exc:
        await require_actor(_request_with_token(raw), session)
    assert exc.value.code == "gone"


async def test_unknown_token_gone_strict_none_lenient(session, space_row):
    request = _request_with_token("bb" * 32)
    with pytest.raises(AppError) as exc:
        await require_actor(request, session)
    assert exc.value.code == "gone"
    assert await resolve_actor(request, session) is None


async def test_private_space_token_404(session, space_row):
    space_row.visibility = "private"
    await session.flush()
    _, raw = await _mint(session, space_row)
    with pytest.raises(AppError) as exc:
        await require_actor(_request_with_token(raw), session)
    assert exc.value.code == "not_found"


async def test_scheduled_space_before_and_after_publish(session, space_row):
    from datetime import timedelta as td
    space_row.visibility = "scheduled"
    space_row.publish_at = datetime.now(timezone.utc) + td(days=1)
    await session.flush()
    _, raw = await _mint(session, space_row)
    with pytest.raises(AppError) as exc:
        await require_actor(_request_with_token(raw), session)
    assert exc.value.code == "not_found"
    space_row.publish_at = datetime.now(timezone.utc) - td(seconds=1)
    await session.flush()
    actor = await require_actor(_request_with_token(raw), session)
    assert isinstance(actor, GuestActor)


async def test_no_credential_401(session):
    request = Request({"type": "http", "method": "GET", "path": "/", "scheme": "http",
                       "server": ("test", 80), "headers": [], "query_string": b""})
    with pytest.raises(AppError) as exc:
        await require_actor(request, session)
    assert exc.value.code == "unauthenticated"
    assert await resolve_actor(request, session) is None


async def test_session_wins_over_token(client, memory_services, session, space_row):
    email = "both@example.com"
    await client.post("/v1/auth/request-code", json={"email": email})
    message = memory_services["mailer"].last_to(email)
    import re
    code = re.search(r"code is: (\d{6})", message.text_body).group(1)
    login = await client.post("/v1/auth/verify", json={"email": email, "code": code})
    _, raw = await _mint(session, space_row)
    me = await client.get("/v1/auth/me", cookies={"ml_session": login.cookies["ml_session"]},
                          headers={"Authorization": f"Bearer {raw}"})
    assert me.json()["data"]["actor"]["type"] == "user"

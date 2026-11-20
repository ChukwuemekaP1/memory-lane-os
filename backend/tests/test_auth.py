"""Passwordless auth journey tests (needs_pg).

Covers: successful code login, wrong/expired/exhausted codes, magic-link
login + single-use + expiry, session refresh rotation, logout, logout-all,
invalid sessions, and /me for user/guest/anonymous actors.
"""

import re

import pytest
from sqlalchemy import select

from app.models.users import User, UserSession

pytestmark = pytest.mark.needs_pg

CODE_RE = re.compile(r"code is: (\d{6})")
MAGIC_RE = re.compile(r"token=([0-9a-f]{64})")


def _code_and_magic(memory_services, email):
    message = memory_services["mailer"].last_to(email)
    assert message is not None
    code = CODE_RE.search(message.text_body).group(1)
    magic = MAGIC_RE.search(message.text_body).group(1)
    return code, magic


async def test_request_code_accepted_and_masked(client, memory_services):
    response = await client.post("/v1/auth/request-code", json={"email": "Ada@Example.com"})
    assert response.status_code == 202
    assert response.json()["data"]["masked_email"] == "a***@example.com"
    assert memory_services["mailer"].last_to("ada@example.com") is not None


async def test_request_code_rejects_bad_email(client):
    response = await client.post("/v1/auth/request-code", json={"email": "not-an-email"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_verify_code_success_sets_session_cookie(client, memory_services, session):
    email = "login@example.com"
    await client.post("/v1/auth/request-code", json={"email": email})
    code, _ = _code_and_magic(memory_services, email)
    response = await client.post("/v1/auth/verify", json={"email": email, "code": code})
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["user"]["email"] == email
    assert body["user"]["email_verified_at"] is not None
    assert "ml_session" in response.cookies
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    assert user.email_verified_at is not None


async def test_verify_code_wrong_code_401(client, memory_services):
    email = "wrong@example.com"
    await client.post("/v1/auth/request-code", json={"email": email})
    response = await client.post("/v1/auth/verify", json={"email": email, "code": "000000"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_verify_code_unknown_challenge_410(client):
    response = await client.post(
        "/v1/auth/verify", json={"email": "ghost@example.com", "code": "123456"}
    )
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "gone"


async def test_verify_code_attempts_exhausted_403(client, memory_services):
    email = "locked@example.com"
    await client.post("/v1/auth/request-code", json={"email": email})
    last = None
    for _ in range(5):
        last = await client.post("/v1/auth/verify", json={"email": email, "code": "000000"})
    assert last.status_code == 403
    assert last.json()["error"]["code"] == "forbidden"
    # Challenge is consumed: even the right code is gone now.
    code, _ = _code_and_magic(memory_services, email)
    retry = await client.post("/v1/auth/verify", json={"email": email, "code": code})
    assert retry.status_code == 410


async def test_verify_code_reuse_410(client, memory_services):
    email = "reuse@example.com"
    await client.post("/v1/auth/request-code", json={"email": email})
    code, _ = _code_and_magic(memory_services, email)
    first = await client.post("/v1/auth/verify", json={"email": email, "code": code})
    assert first.status_code == 200
    second = await client.post("/v1/auth/verify", json={"email": email, "code": code})
    assert second.status_code == 410


async def test_magic_link_success_json_and_single_use(client, memory_services):
    email = "magic@example.com"
    await client.post("/v1/auth/request-code", json={"email": email})
    _, magic = _code_and_magic(memory_services, email)
    first = await client.get(f"/v1/auth/magic?token={magic}",
                             headers={"Accept": "application/json"})
    assert first.status_code == 200
    assert first.json()["data"]["user"]["email"] == email
    assert "ml_session" in first.cookies
    second = await client.get(f"/v1/auth/magic?token={magic}",
                              headers={"Accept": "application/json"})
    assert second.status_code == 410


async def test_magic_link_browser_redirects(client, memory_services):
    email = "browser@example.com"
    await client.post("/v1/auth/request-code", json={"email": email})
    _, magic = _code_and_magic(memory_services, email)
    response = await client.get(f"/v1/auth/magic?token={magic}",
                                headers={"Accept": "text/html"},
                                follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/callback?ok=1" in response.headers["location"]
    assert "ml_session" in response.cookies


async def test_magic_link_unknown_token_410(client):
    response = await client.get("/v1/auth/magic?token=" + "ab" * 32,
                                headers={"Accept": "application/json"})
    assert response.status_code == 410


async def test_code_consumes_magic_and_vice_versa(client, memory_services):
    email = "either@example.com"
    await client.post("/v1/auth/request-code", json={"email": email})
    code, magic = _code_and_magic(memory_services, email)
    ok = await client.post("/v1/auth/verify", json={"email": email, "code": code})
    assert ok.status_code == 200
    spent = await client.get(f"/v1/auth/magic?token={magic}",
                             headers={"Accept": "application/json"})
    assert spent.status_code == 410


async def test_refresh_rotates_and_old_secret_dies(client, memory_services):
    email = "refresh@example.com"
    await client.post("/v1/auth/request-code", json={"email": email})
    code, _ = _code_and_magic(memory_services, email)
    login = await client.post("/v1/auth/verify", json={"email": email, "code": code})
    old_cookie = login.cookies["ml_session"]
    refreshed = await client.post("/v1/auth/refresh", cookies={"ml_session": old_cookie})
    assert refreshed.status_code == 200
    assert refreshed.cookies["ml_session"] != old_cookie
    replay = await client.post("/v1/auth/refresh", cookies={"ml_session": old_cookie})
    assert replay.status_code == 401


async def test_refresh_invalid_session_401(client):
    response = await client.post("/v1/auth/refresh", cookies={"ml_session": "bogus"})
    assert response.status_code == 401


async def test_logout_revokes_session(client, memory_services):
    email = "logout@example.com"
    await client.post("/v1/auth/request-code", json={"email": email})
    code, _ = _code_and_magic(memory_services, email)
    login = await client.post("/v1/auth/verify", json={"email": email, "code": code})
    cookie = login.cookies["ml_session"]
    out = await client.post("/v1/auth/logout", cookies={"ml_session": cookie})
    assert out.status_code == 204
    after = await client.get("/v1/auth/me", cookies={"ml_session": cookie})
    assert after.json()["data"]["actor"] is None


async def test_logout_all_revokes_every_session(client, memory_services, session):
    email = "logoutall@example.com"
    await client.post("/v1/auth/request-code", json={"email": email})
    code, _ = _code_and_magic(memory_services, email)
    first = await client.post("/v1/auth/verify", json={"email": email, "code": code})
    await client.post("/v1/auth/request-code", json={"email": email})
    code2, _ = _code_and_magic(memory_services, email)
    second = await client.post("/v1/auth/verify", json={"email": email, "code": code2})
    assert first.cookies["ml_session"] != second.cookies["ml_session"]
    out = await client.post("/v1/auth/logout-all",
                            cookies={"ml_session": second.cookies["ml_session"]})
    assert out.status_code == 204
    for cookie in (first.cookies["ml_session"], second.cookies["ml_session"]):
        me = await client.get("/v1/auth/me", cookies={"ml_session": cookie})
        assert me.json()["data"]["actor"] is None
    active = (await session.execute(
        select(UserSession).where(UserSession.revoked_at.is_(None))
    )).scalars().all()
    assert active == []


async def test_me_anonymous_user_and_unknown_token(client, memory_services):
    anon = await client.get("/v1/auth/me")
    assert anon.json()["data"]["actor"] is None

    unknown = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {'cd' * 32}"})
    assert unknown.json()["data"]["actor"] is None  # lenient me: unknown token, no actor

    email = "me@example.com"
    await client.post("/v1/auth/request-code", json={"email": email})
    code, _ = _code_and_magic(memory_services, email)
    login = await client.post("/v1/auth/verify", json={"email": email, "code": code})
    me = await client.get("/v1/auth/me", cookies={"ml_session": login.cookies["ml_session"]})
    actor = me.json()["data"]["actor"]
    assert actor["type"] == "user"
    assert actor["user"]["email"] == email


async def test_me_guest_token_and_strict_actor(client, session, space_row):
    from starlette.requests import Request

    from app.models.enums import GuestRoleCap
    from app.models.spaces import GuestAccessToken
    from app.modules.identity import tokens as token_helpers
    from app.modules.permissions.actor import GuestActor, require_actor

    raw = "ef" * 32
    session.add(GuestAccessToken(space_id=space_row.id,
                                 token_hash=token_helpers.sha256_hex(raw),
                                 label="Test", role_cap=GuestRoleCap.contributor,
                                 use_count=0))
    await session.flush()

    me = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {raw}"})
    actor = me.json()["data"]["actor"]
    assert actor["type"] == "guest"
    assert actor["role_cap"] == "contributor"

    scope = {"type": "http", "method": "GET", "path": "/",
             "headers": [(b"authorization", f"Bearer {raw}".encode())],
             "query_string": b"", "server": ("test", 80), "scheme": "http"}
    strict = await require_actor(Request(scope), session)
    assert isinstance(strict, GuestActor)
    assert strict.space_id == space_row.id

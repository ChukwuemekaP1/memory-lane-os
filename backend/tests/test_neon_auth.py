"""Sync tests: Neon Auth JWT verification core (offline RSA keypair)."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import Settings
from app.errors import AppError
from app.modules.identity.neon import NeonAuthVerifier

ISSUER = "https://auth.test.neon"
AUDIENCE = "memory-lane-test"
KID = "test-key-1"


def _keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    numbers = public.public_numbers()
    n = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    e = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
    import base64

    def b64url(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    jwks = {"keys": [{"kty": "RSA", "kid": KID, "use": "sig", "alg": "RS256",
                      "n": b64url(n), "e": b64url(e)}]}
    pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    return pem, jwks


def _settings(**overrides):
    base = dict(environment="test", database_url="postgresql+asyncpg://u:p@h/db",
                neon_auth_enabled=True, neon_auth_issuer=ISSUER,
                neon_auth_audience=AUDIENCE)
    base.update(overrides)
    return Settings(**base)


def _mint(pem, claims, headers=None):
    return jwt.encode(claims, pem, algorithm="RS256",
                      headers={"kid": KID, **(headers or {})})


@pytest.fixture(scope="module")
def keys():
    return _keypair()


@pytest.fixture
def verifier():
    return NeonAuthVerifier(_settings(neon_auth_jwks_json='{"keys": []}'))


def _claims(**overrides):
    now = int(time.time())
    base = {"sub": "neon-user-123", "email": "Ada@Example.com", "name": "Ada",
            "email_verified": True, "iss": ISSUER, "aud": AUDIENCE,
            "exp": now + 600, "iat": now}
    base.update(overrides)
    return base


def test_valid_token_accepted(verifier, keys):
    pem, jwks = keys
    identity = verifier.verify_with_jwks(_mint(pem, _claims()), jwks)
    assert identity.sub == "neon-user-123"
    assert identity.email == "Ada@Example.com"
    assert identity.email_verified is True


def test_wrong_signature_rejected(verifier, keys):
    _, jwks = keys
    other_pem, _ = _keypair()
    with pytest.raises(AppError) as exc:
        verifier.verify_with_jwks(_mint(other_pem, _claims()), jwks)
    assert exc.value.code == "unauthenticated"


def test_expired_rejected(verifier, keys):
    pem, jwks = keys
    with pytest.raises(AppError):
        verifier.verify_with_jwks(_mint(pem, _claims(exp=int(time.time()) - 10)), jwks)


def test_wrong_issuer_audience_rejected(verifier, keys):
    pem, jwks = keys
    with pytest.raises(AppError):
        verifier.verify_with_jwks(_mint(pem, _claims(iss="https://evil.test")), jwks)
    with pytest.raises(AppError):
        verifier.verify_with_jwks(_mint(pem, _claims(aud="other-app")), jwks)


def test_missing_sub_rejected(verifier, keys):
    pem, jwks = keys
    claims = _claims()
    del claims["sub"]
    with pytest.raises(AppError):
        verifier.verify_with_jwks(_mint(pem, claims), jwks)


def test_wrong_algorithm_rejected(verifier, keys):
    pem, jwks = keys
    hs_token = jwt.encode(_claims(), "secret", algorithm="HS256")
    with pytest.raises(AppError):
        verifier.verify_with_jwks(hs_token, jwks)
    assert pem is not None


def test_malformed_and_unknown_kid_rejected(verifier, keys):
    pem, jwks = keys
    with pytest.raises(AppError):
        verifier.verify_with_jwks("not-a-jwt", jwks)
    with pytest.raises(AppError):
        verifier.verify_with_jwks(_mint(pem, _claims(), {"kid": "unknown"}), jwks)


def test_disabled_or_misconfigured_verifier():
    with pytest.raises(AppError):
        NeonAuthVerifier(_settings(neon_auth_enabled=False))
    with pytest.raises(AppError):
        NeonAuthVerifier(_settings(neon_auth_issuer=""))
    with pytest.raises(AppError):
        NeonAuthVerifier(_settings(neon_auth_audience=""))
    with pytest.raises(AppError):
        NeonAuthVerifier(_settings())  # no JWKS source at all


@pytest.mark.needs_pg
async def test_jwt_bearer_end_to_end(client, monkeypatch):
    import json

    from app.config import reset_settings_cache
    from app.modules.identity.neon import reset_neon_verifier

    pem, jwks = _keypair()
    monkeypatch.setenv("NEON_AUTH_ENABLED", "true")
    monkeypatch.setenv("NEON_AUTH_ISSUER", ISSUER)
    monkeypatch.setenv("NEON_AUTH_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("NEON_AUTH_JWKS_JSON", json.dumps(jwks))
    reset_settings_cache()
    reset_neon_verifier()
    try:
        token = _mint(pem, _claims())
        first = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert first.json()["data"]["actor"]["type"] == "user"
        assert first.json()["data"]["actor"]["user"]["email"] == "ada@example.com"
        user_id = first.json()["data"]["actor"]["user"]["id"]
        # Second sighting resolves the SAME provisioned user.
        second = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert second.json()["data"]["actor"]["user"]["id"] == user_id
        # Forged token fails closed.
        bad = await client.get("/v1/auth/me", headers={"Authorization": "Bearer a.b.c"})
        assert bad.json()["data"]["actor"] is None
    finally:
        reset_settings_cache()
        reset_neon_verifier()


@pytest.mark.needs_pg
async def test_jwt_ignored_when_disabled(client):
    response = await client.get("/v1/auth/me", headers={"Authorization": "Bearer a.b.c"})
    assert response.json()["data"]["actor"] is None


@pytest.mark.needs_pg
async def test_admin_access_writes_audit_row(client, memory_services, session):
    from sqlalchemy import select

    from app.models.audit import AuditEvent
    from app.models.users import User
    from tests.helpers import create_space, login_as

    cookie = await login_as(client, memory_services, "audit-owner@example.com")
    themes = await client.get("/v1/themes", cookies={"ml_session": cookie})
    theme_id = next(t for t in themes.json()["data"] if t["plan_required"] == "free")["id"]
    data = await create_space(client, cookie, theme_id, visibility="private")
    admin_cookie = await login_as(client, memory_services, "root-admin@example.com")
    async with session.begin_nested():
        admin = (await session.execute(
            select(User).where(User.email == "root-admin@example.com"))).scalar_one()
        from app.models.enums import GlobalRole

        admin.role_global = GlobalRole.admin
    await session.flush()
    response = await client.get(f"/v1/spaces/{data['space']['id']}",
                                cookies={"ml_session": admin_cookie})
    assert response.status_code == 200
    rows = (await session.execute(select(AuditEvent).where(
        AuditEvent.action == "admin.space.read"))).scalars().all()
    assert len(rows) == 1
    assert str(rows[0].space_id) == data["space"]["id"]

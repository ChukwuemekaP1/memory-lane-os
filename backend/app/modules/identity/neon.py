"""Neon Auth (Better Auth) JWT verification.

Verifies bearer JWTs against a JWKS: signature (EdDSA/RS256/ES256), issuer,
audience, expiration, and required `sub` claim. The JWKS comes from inline JSON
(tests/small deployments) or is fetched + cached from the configured URL.
Keys and tokens are never logged.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.config import Settings
from app.errors import AppError
from app.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class NeonIdentity:
    sub: str
    email: str | None
    name: str | None
    email_verified: bool


ALLOWED_ALGORITHMS = ("EdDSA", "RS256", "ES256")


class NeonAuthVerifier:
    def __init__(self, settings: Settings,
                 jwks_fetcher: Any | None = None) -> None:
        if not settings.neon_auth_enabled:
            raise AppError("forbidden", "Neon Auth is not enabled.", 403)
        if not settings.neon_auth_issuer or not settings.neon_auth_audience:
            raise AppError("internal_error", "Neon Auth is misconfigured (issuer/audience).", 500)
        if not settings.neon_auth_jwks_json and not settings.neon_auth_jwks_url:
            raise AppError("internal_error", "Neon Auth is misconfigured (no JWKS source).", 500)
        self._settings = settings
        self._fetcher = jwks_fetcher
        self._cached_jwks: dict[str, Any] | None = None
        self._cached_at: float = 0.0
        self._jwks_client: PyJWKClient | None = None

    def _inline_jwks(self) -> dict[str, Any] | None:
        raw = self._settings.neon_auth_jwks_json.strip()
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except ValueError:
            raise AppError("internal_error", "Neon Auth inline JWKS is invalid JSON.", 500) from None
        if not isinstance(data, dict) or "keys" not in data:
            raise AppError("internal_error", "Neon Auth inline JWKS has no keys.", 500)
        return data

    async def _remote_jwks(self) -> dict[str, Any]:
        now = time.time()
        if self._cached_jwks is not None and now - self._cached_at < self._settings.neon_auth_jwks_ttl_seconds:
            return self._cached_jwks
        if self._fetcher is not None:
            data = await self._fetcher(self._settings.neon_auth_jwks_url)
        else:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.get(self._settings.neon_auth_jwks_url)
                    response.raise_for_status()
                    data = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise AppError("upstream_error", "Could not fetch Neon Auth keys.", 502,
                               retryable=True) from exc
        if not isinstance(data, dict) or "keys" not in data:
            raise AppError("upstream_error", "Neon Auth keys are malformed.", 502,
                           retryable=True)
        self._cached_jwks, self._cached_at = data, now
        return data

    def _key_for(self, jwks: dict[str, Any], kid: str | None):  # type: ignore[no-untyped-def]
        from jwt import PyJWK

        for entry in jwks.get("keys", []):
            if kid is None or entry.get("kid") == kid:
                try:
                    return PyJWK(entry).key
                except Exception as exc:
                    raise AppError("unauthenticated", "Unusable signing key.", 401) from exc
        raise AppError("unauthenticated", "Unknown token signing key.", 401)

    async def verify(self, raw_token: str) -> NeonIdentity:
        jwks = self._inline_jwks() or await self._remote_jwks()
        return self.verify_with_jwks(raw_token, jwks)

    def verify_with_jwks(self, raw_token: str, jwks: dict[str, Any]) -> NeonIdentity:
        """Sync verification core (crypto + claims). Fully unit-testable."""
        token = (raw_token or "").strip()
        if token.count(".") != 2:
            raise AppError("unauthenticated", "Malformed credentials.", 401)
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise AppError("unauthenticated", "Malformed credentials.", 401) from None
        alg = header.get("alg")
        if alg not in ALLOWED_ALGORITHMS:
            raise AppError("unauthenticated", "Unexpected token algorithm.", 401)
        key = self._key_for(jwks, header.get("kid"))
        try:
            claims = jwt.decode(
                token, key, algorithms=[alg],
                issuer=self._settings.neon_auth_issuer,
                audience=self._settings.neon_auth_audience,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.ExpiredSignatureError:
            raise AppError("unauthenticated", "Session has expired.", 401) from None
        except jwt.InvalidIssuerError:
            raise AppError("unauthenticated", "Token issuer not trusted.", 401) from None
        except jwt.InvalidAudienceError:
            raise AppError("unauthenticated", "Token audience mismatch.", 401) from None
        except jwt.InvalidTokenError:
            raise AppError("unauthenticated", "Invalid session token.", 401) from None
        sub = claims.get("sub")
        if not sub or not isinstance(sub, str):
            raise AppError("unauthenticated", "Token has no subject.", 401)
        email = claims.get("email")
        email_verified = bool(
            claims.get("email_verified")
            if "email_verified" in claims
            else claims.get("emailVerified", False)
        )
        logger.info("neon token verified")
        return NeonIdentity(
            sub=sub,
            email=email if isinstance(email, str) else None,
            name=claims.get("name") if isinstance(claims.get("name"), str) else None,
            email_verified=email_verified,
        )


_verifier: NeonAuthVerifier | None = None


def get_neon_verifier(settings: Settings | None = None) -> NeonAuthVerifier:
    global _verifier
    if _verifier is not None:
        return _verifier
    if settings is None:
        from app.config import get_settings

        settings = get_settings()
    _verifier = NeonAuthVerifier(settings)
    return _verifier


def reset_neon_verifier() -> None:
    global _verifier
    _verifier = None

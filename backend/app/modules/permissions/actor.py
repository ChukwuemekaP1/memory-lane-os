"""Actor resolution: session user first, guest token second (PERMISSIONS_MATRIX).

Lenient `resolve_actor` returns None for missing/invalid credentials (for
public reads and /auth/me). Strict `require_actor` raises the precise error:
410 gone for revoked/expired/exhausted tokens, 404 for invisible spaces,
401 when no usable credential is present.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import AppError
from app.logging import get_logger
from app.models.enums import GuestRoleCap, SpaceVisibility
from app.models.spaces import GuestAccessToken, Space
from app.modules.identity import tokens
from app.modules.identity.service import load_session_user

logger = get_logger(__name__)


@dataclass(frozen=True)
class UserActor:
    user_id: UUID
    email: str
    display_name: str
    is_admin: bool
    session_id: UUID


@dataclass(frozen=True)
class GuestActor:
    space_id: UUID
    token_id: UUID
    role_cap: GuestRoleCap
    label: str


Actor = UserActor | GuestActor


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    scheme, _, credential = auth.partition(" ")
    if scheme.lower() == "bearer" and credential.strip():
        return credential.strip()
    query_token = request.query_params.get("guest")
    return query_token.strip() if query_token else None


async def _session_actor(request: Request, session: AsyncSession) -> UserActor | None:
    from app.config import get_settings

    settings = get_settings()
    if settings.neon_auth_enabled:
        return None  # single active session model: never mix Neon Auth with custom cookies
    raw = request.cookies.get(settings.session_cookie_name)
    if not raw:
        return None
    parsed = tokens.parse_session_cookie(raw)
    if parsed is None:
        return None
    loaded = await load_session_user(session, parsed.session_id, parsed.refresh_secret)
    if loaded is None:
        return None
    user, row = loaded
    return UserActor(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.role_global == "admin",
        session_id=row.id,
    )


async def _claim_guest_token(
    session: AsyncSession, raw_token: str
) -> tuple[GuestAccessToken, Space]:
    """Validate a guest token and atomically consume one use. Raises AppError."""
    token_hash = tokens.sha256_hex(raw_token)
    result = await session.execute(
        select(GuestAccessToken).where(GuestAccessToken.token_hash == token_hash)
    )
    token = result.scalar_one_or_none()
    if token is None or token.revoked_at is not None:
        raise AppError("gone", "This invite link is no longer valid.", 410)
    if token.expires_at is not None and token.expires_at <= _utcnow():
        raise AppError("gone", "This invite link has expired.", 410)
    space = await session.get(Space, token.space_id)
    if space is None or space.deleted_at is not None:
        raise AppError("not_found", "Space not found.", 404)
    visible = (
        space.visibility in (SpaceVisibility.link, SpaceVisibility.public)
        or (
            space.visibility == SpaceVisibility.scheduled
            and space.publish_at is not None
            and space.publish_at <= _utcnow()
        )
    )
    if not visible:
        raise AppError("not_found", "Space not found.", 404)
    claimed = await session.execute(
        update(GuestAccessToken)
        .where(
            GuestAccessToken.id == token.id,
            (GuestAccessToken.max_uses.is_(None))
            | (GuestAccessToken.use_count < GuestAccessToken.max_uses),
        )
        .values(use_count=GuestAccessToken.use_count + 1)
    )
    if claimed.rowcount != 1:
        raise AppError("gone", "This invite link has reached its use limit.", 410)
    await session.flush()
    return token, space


def _looks_like_jwt(raw_token: str) -> bool:
    return raw_token.count(".") == 2


async def _neon_actor(request: Request, session: AsyncSession) -> UserActor | None:
    """Neon Auth JWT bearer path (only when enabled). None when not applicable."""
    from sqlalchemy import select

    from app.config import get_settings
    from app.models.users import User

    settings = get_settings()
    if not settings.neon_auth_enabled:
        return None
    raw_token = _bearer_token(request)
    if not raw_token or not _looks_like_jwt(raw_token):
        return None
    from app.modules.identity.neon import get_neon_verifier

    identity = await get_neon_verifier(settings).verify(raw_token)
    result = await session.execute(select(User).where(User.neon_auth_sub == identity.sub))
    user = result.scalar_one_or_none()
    if user is None and identity.email:
        maybe = await session.execute(
            select(User).where(User.email == identity.email.lower()))
        existing = maybe.scalar_one_or_none()
        if existing is not None and existing.deleted_at is None and identity.email_verified:
            existing.neon_auth_sub = identity.sub  # link verified email
            user = existing
    if user is None:
        if identity.email:
            clash = await session.execute(
                select(User).where(User.email == identity.email.lower()))
            if clash.scalar_one_or_none() is not None:
                raise AppError("unauthenticated",
                               "This email is linked to another sign-in method.", 401)
        user = User(
            email=(identity.email or f"{identity.sub}@neon.local").lower(),
            display_name=(identity.name or "Member")[:80],
            locale="en", timezone="Africa/Lagos", marketing_opt_in=False,
            neon_auth_sub=identity.sub,
            email_verified_at=_utcnow() if identity.email_verified else None,
        )
        session.add(user)
        await session.flush()
    if user.deleted_at is not None:
        raise AppError("forbidden", "This account is closed.", 403)
    # Synchronize profile attributes from verified Neon Auth claims.
    changed = False
    if identity.name and identity.name.strip() and user.display_name != identity.name.strip()[:80]:
        user.display_name = identity.name.strip()[:80]
        changed = True
    if identity.email_verified and user.email_verified_at is None:
        user.email_verified_at = _utcnow()
        changed = True
    if changed:
        await session.flush()
    return UserActor(
        user_id=user.id, email=user.email, display_name=user.display_name,
        is_admin=user.role_global == "admin",
        session_id=uuid.uuid5(uuid.NAMESPACE_URL, f"neon-auth:{identity.sub}"),
    )


async def resolve_actor(request: Request, session: AsyncSession) -> Actor | None:
    """Lenient resolution: session wins, then Neon JWT, then guest token."""
    user_actor = await _session_actor(request, session)
    if user_actor is not None:
        return user_actor
    try:
        neon_actor = await _neon_actor(request, session)
    except AppError:
        return None
    if neon_actor is not None:
        return neon_actor
    raw_token = _bearer_token(request)
    if not raw_token:
        return None
    try:
        token, space = await _claim_guest_token(session, raw_token)
    except AppError:
        return None
    return GuestActor(
        space_id=space.id, token_id=token.id, role_cap=token.role_cap, label=token.label
    )


async def require_actor(request: Request, session: AsyncSession) -> Actor:
    """Strict resolution with precise errors (401/404/410)."""
    user_actor = await _session_actor(request, session)
    if user_actor is not None:
        return user_actor
    raw_token = _bearer_token(request)
    if not raw_token:
        raise AppError("unauthenticated", "Authentication required.", 401)
    from app.config import get_settings

    if get_settings().neon_auth_enabled and _looks_like_jwt(raw_token):
        neon_actor = await _neon_actor(request, session)
        if neon_actor is None:  # pragma: no cover (verify raises instead)
            raise AppError("unauthenticated", "Authentication required.", 401)
        return neon_actor
    token, space = await _claim_guest_token(session, raw_token)
    return GuestActor(
        space_id=space.id, token_id=token.id, role_cap=token.role_cap, label=token.label
    )


async def get_actor(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> Actor | None:
    return await resolve_actor(request, session)


async def require_actor_dep(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> Actor:
    return await require_actor(request, session)


async def require_user(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> UserActor:
    actor = await require_actor(request, session)
    if not isinstance(actor, UserActor):
        raise AppError("forbidden", "A Memory Lane account is required.", 403)
    return actor

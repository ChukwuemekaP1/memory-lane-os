"""Identity routes: passwordless auth (API_SPECIFICATION Section 6)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import get_session
from app.deps import SettingsDep, get_job_runner_dep, get_otp_store_dep, get_rate_limiter_dep
from app.errors import AppError, ok_payload
from app.modules.identity import service, tokens
from app.modules.identity.schemas import (
    GuestActorOut,
    MeOut,
    RequestCodeIn,
    RequestCodeOut,
    SessionOut,
    UserActorOut,
    UserOut,
    VerifyCodeIn,
)
from app.modules.permissions.actor import GuestActor, UserActor, get_actor
from app.services.jobs import JobRunner, get_job_runner
from app.services.otp_store import OtpStore, get_otp_store
from app.services.ratelimit import RateLimiter, get_rate_limiter

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    if request.client is not None:
        return request.client.host
    return None


async def _rate_limit(
    limiter: RateLimiter, key: str, limit: int, window_seconds: int
) -> None:
    result = await limiter.check(key, limit, window_seconds)
    if not result.allowed:
        raise AppError(
            "rate_limited", "Too many requests. Please slow down.", 429, retryable=True,
            headers={"Retry-After": str(result.retry_after_seconds)},
        )


def _set_session_cookie(response: Response, settings: Settings, value: str,
                         max_age: int) -> None:
    response.set_cookie(
        settings.session_cookie_name, value, httponly=True,
        secure=settings.session_cookie_secure, samesite="lax", path="/", max_age=max_age,
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")


def _user_out(user) -> UserOut:  # type: ignore[no-untyped-def]
    return UserOut(
        id=user.id, email=user.email, display_name=user.display_name,
        email_verified_at=user.email_verified_at, role_global=user.role_global.value,
    )


def _reject_if_neon_auth(settings: Settings) -> None:
    if settings.neon_auth_enabled:
        raise AppError(
            "conflict",
            "Neon Managed Auth is active; custom passwordless sessions are disabled.",
            409,
        )


@router.post("/request-code", status_code=status.HTTP_202_ACCEPTED)
async def request_code(
    body: RequestCodeIn,
    request: Request,
    settings: SettingsDep,
    session: Annotated[AsyncSession, Depends(get_session)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter_dep)],
    otp_store: Annotated[OtpStore, Depends(get_otp_store_dep)],
    jobs: Annotated[JobRunner, Depends(get_job_runner_dep)],
) -> dict:
    _reject_if_neon_auth(settings)
    email = tokens.normalize_email(body.email)
    await _rate_limit(limiter, f"otp:req:{email}:{_client_ip(request)}", 5, 600)
    masked = await service.request_challenge(session, email, _client_ip(request),
                                             settings, otp_store, jobs)
    return ok_payload(RequestCodeOut(masked_email=masked).model_dump(mode="json"))


@router.post("/verify")
async def verify_code(
    body: VerifyCodeIn,
    request: Request,
    response: Response,
    settings: SettingsDep,
    session: Annotated[AsyncSession, Depends(get_session)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter_dep)],
    otp_store: Annotated[OtpStore, Depends(get_otp_store_dep)],
) -> dict:
    _reject_if_neon_auth(settings)
    email = tokens.normalize_email(body.email)
    await _rate_limit(limiter, f"otp:verify:{email}:{_client_ip(request)}", 10, 600)
    user, row, secret = await service.verify_code(
        session, email, body.code, _client_ip(request),
        (request.headers.get("user-agent") or "")[:200], settings, otp_store,
    )
    _set_session_cookie(response, settings, tokens.build_session_cookie(row.id, secret),
                        settings.session_ttl_hours * 3600)
    return ok_payload(
        SessionOut(user=_user_out(user), session_expires_at=row.expires_at)
        .model_dump(mode="json")
    )


@router.get("/magic")
async def magic_link(
    request: Request,
    response: Response,
    settings: SettingsDep,
    session: Annotated[AsyncSession, Depends(get_session)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter_dep)],
    otp_store: Annotated[OtpStore, Depends(get_otp_store_dep)],
    token: str = Query(min_length=16, max_length=128),
):
    _reject_if_neon_auth(settings)
    await _rate_limit(limiter, f"otp:magic:{_client_ip(request)}", 10, 600)
    user, row, secret = await service.verify_magic(
        session, token, _client_ip(request),
        (request.headers.get("user-agent") or "")[:200], settings, otp_store,
    )
    cookie_value = tokens.build_session_cookie(row.id, secret)
    wants_json = "application/json" in (request.headers.get("accept") or "")
    if wants_json:
        _set_session_cookie(response, settings, cookie_value,
                            settings.session_ttl_hours * 3600)
        return ok_payload(
            SessionOut(user=_user_out(user), session_expires_at=row.expires_at)
            .model_dump(mode="json")
        )
    redirect = RedirectResponse(
        f"{settings.frontend_base_url.rstrip('/')}/auth/callback?ok=1",
        status_code=status.HTTP_302_FOUND,
    )
    _set_session_cookie(redirect, settings, cookie_value, settings.session_ttl_hours * 3600)
    return redirect


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    settings: SettingsDep,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    _reject_if_neon_auth(settings)
    raw = request.cookies.get(settings.session_cookie_name)
    parsed = tokens.parse_session_cookie(raw or "")
    if parsed is None:
        raise AppError("unauthenticated", "Session is invalid or expired.", 401)
    user, row, secret = await service.refresh_session(
        session, parsed.session_id, parsed.refresh_secret, settings
    )
    _set_session_cookie(response, settings, tokens.build_session_cookie(row.id, secret),
                        settings.session_ttl_hours * 3600)
    return ok_payload({"session_expires_at": row.expires_at.isoformat()})


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    settings: SettingsDep,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    raw = request.cookies.get(settings.session_cookie_name)
    parsed = tokens.parse_session_cookie(raw or "")
    if parsed is not None:
        await service.logout(session, parsed.session_id)
    _clear_session_cookie(response, settings)
    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    request: Request,
    response: Response,
    settings: SettingsDep,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[object, Depends(get_actor)],
) -> Response:
    if isinstance(actor, UserActor):
        await service.logout_all(session, actor.user_id)
    _clear_session_cookie(response, settings)
    return response


@router.get("/me")
async def me(
    actor: Annotated[object, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    if isinstance(actor, UserActor):
        from app.models.users import User

        user = await session.get(User, actor.user_id)
        if user is None:
            raise AppError("unauthenticated", "Session is invalid or expired.", 401)
        payload = MeOut(actor=UserActorOut(user=_user_out(user))).model_dump(mode="json")
    elif isinstance(actor, GuestActor):
        payload = MeOut(
            actor=GuestActorOut(
                space_id=actor.space_id, role_cap=actor.role_cap.value, label=actor.label
            )
        ).model_dump(mode="json")
    else:
        payload = MeOut(actor=None).model_dump(mode="json")
    return ok_payload(payload)

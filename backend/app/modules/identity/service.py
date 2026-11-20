"""Identity service: challenges, verification, sessions (DATA_FLOW Section 3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import AppError
from app.logging import get_logger
from app.models.users import OtpChallenge, User, UserSession
from app.modules.identity import tokens
from app.services.jobs import JobRunner
from app.services.otp_store import OtpRecord, OtpStore

logger = get_logger(__name__)

EXPIRED = AppError("gone", "This code or link has expired. Request a new one.", 410)
INVALID_CODE = AppError("unauthenticated", "Invalid code.", 401)
TOO_MANY = AppError("forbidden", "Too many attempts. Request a new code.", 403)
BAD_SESSION = AppError("unauthenticated", "Session is invalid or expired.", 401)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def request_challenge(
    session: AsyncSession,
    email: str,
    ip: str | None,
    settings: Settings,
    otp_store: OtpStore,
    jobs: JobRunner,
) -> str:
    """Issue an OTP + magic link challenge. Always succeeds identically
    (no account oracle) — unknown emails get the same response."""
    normalized = tokens.normalize_email(email)
    code = tokens.generate_code()
    magic_token = tokens.generate_magic_token()
    ttl = settings.otp_ttl_minutes * 60

    record = OtpRecord(
        email=normalized,
        code_hash=tokens.sha256_hex(code),
        magic_hash=tokens.sha256_hex(magic_token),
        attempts=0,
        expires_at=0,  # set by the store
    )
    await otp_store.save(record, ttl)
    session.add(
        OtpChallenge(
            email=normalized,
            code_hash=record.code_hash,
            magic_hash=record.magic_hash,
            attempts=0,
            expires_at=_utcnow() + timedelta(seconds=ttl),
            ip_request=ip,
        )
    )
    await session.flush()

    magic_url = f"{settings.frontend_base_url.rstrip('/')}/auth/magic?token={magic_token}"
    await jobs.enqueue(
        "send_email",
        {
            "to": normalized,
            "subject": "Your Memory Lane sign-in code",
            "template": "otp_v1",
            "text_body": (
                f"Your Memory Lane sign-in code is: {code}\n\n"
                f"It expires in {settings.otp_ttl_minutes} minutes.\n\n"
                f"Or sign in instantly with this link (single use):\n{magic_url}\n"
            ),
        },
        idempotency_key=f"otp:{record.magic_hash}",
    )
    logger.info("challenge issued for email hash=%s", tokens.sha256_hex(normalized)[:12])
    return tokens.mask_email(normalized)


async def _consume_challenge(
    session: AsyncSession, otp_store: OtpStore, record: OtpRecord
) -> None:
    await otp_store.consume(record.magic_hash)
    await session.execute(
        update(OtpChallenge)
        .where(OtpChallenge.magic_hash == record.magic_hash,
               OtpChallenge.consumed_at.is_(None))
        .values(consumed_at=_utcnow())
    )


async def _mirror_attempts(session: AsyncSession, record: OtpRecord) -> None:
    await session.execute(
        update(OtpChallenge)
        .where(OtpChallenge.magic_hash == record.magic_hash)
        .values(attempts=record.attempts)
    )


async def _get_or_create_user(session: AsyncSession, email: str) -> User:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        if user.deleted_at is not None:
            raise AppError("forbidden", "This account is closed.", 403)
        return user
    display_name = email.partition("@")[0][:80] or "Friend"
    user = User(
        email=email,
        display_name=display_name,
        locale="en",
        timezone="Africa/Lagos",
        marketing_opt_in=False,
    )
    session.add(user)
    await session.flush()
    return user


async def _create_session(
    session: AsyncSession, user: User, ip: str | None, device_label: str | None,
    settings: Settings,
) -> tuple[UserSession, str]:
    secret = tokens.generate_refresh_secret()
    row = UserSession(
        user_id=user.id,
        refresh_hash=tokens.sha256_hex(secret),
        device_label=(device_label or "")[:200] or None,
        ip_created=ip,
        expires_at=_utcnow() + timedelta(hours=settings.session_ttl_hours),
    )
    session.add(row)
    await session.flush()
    return row, secret


async def _finalize_verification(
    session: AsyncSession,
    otp_store: OtpStore,
    record: OtpRecord,
    ip: str | None,
    device_label: str | None,
    settings: Settings,
) -> tuple[User, UserSession, str]:
    await _consume_challenge(session, otp_store, record)
    user = await _get_or_create_user(session, record.email)
    if user.email_verified_at is None:
        user.email_verified_at = _utcnow()
    row, secret = await _create_session(session, user, ip, device_label, settings)
    return user, row, secret


async def verify_code(
    session: AsyncSession,
    email: str,
    code: str,
    ip: str | None,
    device_label: str | None,
    settings: Settings,
    otp_store: OtpStore,
) -> tuple[User, UserSession, str]:
    normalized = tokens.normalize_email(email)
    record = await otp_store.load_by_email(normalized)
    if record is None:
        raise EXPIRED
    if record.attempts >= settings.otp_max_attempts:
        await _consume_challenge(session, otp_store, record)
        raise TOO_MANY
    if not tokens.secrets_equal(tokens.sha256_hex(code), record.code_hash):
        attempts = await otp_store.bump_attempts(record.magic_hash)
        record.attempts = attempts or record.attempts + 1
        await _mirror_attempts(session, record)
        if record.attempts >= settings.otp_max_attempts:
            await _consume_challenge(session, otp_store, record)
            raise TOO_MANY
        raise INVALID_CODE
    return await _finalize_verification(session, otp_store, record, ip, device_label, settings)


async def verify_magic(
    session: AsyncSession,
    raw_token: str,
    ip: str | None,
    device_label: str | None,
    settings: Settings,
    otp_store: OtpStore,
) -> tuple[User, UserSession, str]:
    record = await otp_store.load_by_magic(tokens.sha256_hex(raw_token.strip()))
    if record is None:
        raise EXPIRED  # unknown, expired, or already consumed: identical response
    if record.attempts >= settings.otp_max_attempts:
        await _consume_challenge(session, otp_store, record)
        raise TOO_MANY
    return await _finalize_verification(session, otp_store, record, ip, device_label, settings)


async def load_session_user(
    session: AsyncSession, session_id: UUID, secret: str
) -> tuple[User, UserSession] | None:
    """Lenient session validation for actor resolution. None when invalid."""
    row = await session.get(UserSession, session_id)
    if row is None or row.revoked_at is not None or row.expires_at <= _utcnow():
        return None
    if not tokens.secrets_equal(tokens.sha256_hex(secret), row.refresh_hash):
        return None
    user = await session.get(User, row.user_id)
    if user is None or user.deleted_at is not None:
        return None
    if row.last_seen_at <= _utcnow() - timedelta(minutes=5):
        row.last_seen_at = _utcnow()
    return user, row


async def refresh_session(
    session: AsyncSession, session_id: UUID, secret: str, settings: Settings
) -> tuple[User, UserSession, str]:
    loaded = await load_session_user(session, session_id, secret)
    if loaded is None:
        raise BAD_SESSION
    user, row = loaded
    new_secret = tokens.generate_refresh_secret()
    row.refresh_hash = tokens.sha256_hex(new_secret)
    row.last_seen_at = _utcnow()
    row.expires_at = _utcnow() + timedelta(hours=settings.session_ttl_hours)
    await session.flush()
    return user, row, new_secret


async def logout(session: AsyncSession, session_id: UUID) -> None:
    await session.execute(
        update(UserSession)
        .where(UserSession.id == session_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=_utcnow())
    )


async def logout_all(session: AsyncSession, user_id: UUID) -> int:
    result = await session.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=_utcnow())
    )
    return result.rowcount

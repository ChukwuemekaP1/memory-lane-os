"""Archives service: export requests, secure downloads, preservation."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.logging import get_logger
from app.models.archives import Archive, Subscription
from app.models.enums import ArchiveKind, ArchiveStatus, Plan
from app.models.spaces import Space
from app.models.users import User, UserSession
from app.modules.identity import tokens as token_helpers
from app.modules.permissions.actor import UserActor
from app.modules.permissions.capabilities import SpaceContext
from app.services.jobs import JobRunner

logger = get_logger(__name__)

EXPORT_TTL_DAYS = 7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_kind(value: str) -> ArchiveKind:
    try:
        kind = ArchiveKind(value)
    except ValueError:
        valid = ", ".join(k.value for k in ArchiveKind if k != ArchiveKind.purge)
        raise AppError("validation_error", f"Invalid kind. Expected one of: {valid}.", 422) from None
    if kind == ArchiveKind.purge:
        raise AppError("validation_error", "Use the purge endpoint for deletion.", 422)
    return kind


async def _owner_plan(session: AsyncSession, owner_id: UUID) -> Plan:
    result = await session.execute(
        select(Subscription.plan).where(
            Subscription.user_id == owner_id,
            Subscription.status.in_(["active", "past_due"])))
    plan = result.scalar_one_or_none()
    return plan if plan is not None else Plan.free


async def request_export(
    session: AsyncSession, ctx: SpaceContext, kind: str, jobs: JobRunner,
) -> Archive:
    from app.modules.permissions import capabilities as caps

    parsed = _parse_kind(kind)
    if not caps.can_export(ctx, parsed.value):
        if ctx.actor is None:
            raise AppError("unauthenticated", "Authentication required.", 401)
        raise AppError("forbidden", "You may not run this export.", 403)
    if parsed in (ArchiveKind.book_pdf, ArchiveKind.film_mp4):
        if await _owner_plan(session, ctx.space.owner_id) != Plan.premium:
            raise AppError("quota_exceeded", f"{parsed.value} exports need premium.", 403)
    archive = Archive(
        space_id=ctx.space.id, requested_by=ctx.user_id, kind=parsed,
        status=ArchiveStatus.queued, idempotency_key=f"export:{ctx.space.id}:{uuid.uuid4().hex}",
    )
    session.add(archive)
    await session.flush()
    await jobs.enqueue("build_archive", {"archive_id": str(archive.id)},
                       idempotency_key=archive.idempotency_key)
    logger.info("export requested space=%s kind=%s", ctx.space.id, parsed.value)
    return archive


async def list_exports(session: AsyncSession, ctx: SpaceContext) -> list[Archive]:
    from app.modules.permissions import capabilities as caps

    caps.require_staff(ctx)
    await _expire_sweep(session, ctx.space.id)
    result = await session.execute(
        select(Archive).where(Archive.space_id == ctx.space.id,
                              Archive.kind != ArchiveKind.purge)
        .order_by(Archive.created_at.desc()).limit(50))
    return list(result.scalars().all())


async def _expire_sweep(session: AsyncSession, space_id: UUID) -> None:
    from app.services.storage import get_storage

    result = await session.execute(select(Archive).where(
        Archive.space_id == space_id, Archive.status == ArchiveStatus.succeeded,
        Archive.expires_at.is_not(None), Archive.expires_at <= _utcnow()))
    storage = get_storage()
    for archive in result.scalars().all():
        archive.status = ArchiveStatus.expired
        try:
            await storage.delete(_export_key(archive))
        except Exception:
            logger.warning("export sweep delete failed id=%s", archive.id)
    await session.flush()


def _export_key(archive: Archive) -> str:
    ext = {"full_zip": "zip", "book_pdf": "pdf", "film_mp4": "mp4",
           "data_export": "zip"}[archive.kind.value]
    scope = str(archive.space_id) if archive.space_id else f"user/{archive.requested_by}"
    return f"exports/{scope}/{archive.id}.{ext}"


async def download_url_for(session: AsyncSession, actor, archive_id: UUID,
                           raw_token: str | None) -> str:
    """Owner-session or share-token download. Enforces expiry + permissions."""
    from app.modules.permissions import capabilities as caps
    from app.services.storage import get_storage

    archive = await session.get(Archive, archive_id)
    if archive is None or archive.status != ArchiveStatus.succeeded:
        raise AppError("not_found", "Export not found.", 404)
    if archive.expires_at is not None and archive.expires_at <= _utcnow():
        archive.status = ArchiveStatus.expired
        await session.flush()
        raise AppError("gone", "This download link has expired.", 410)
    if raw_token:
        if archive.download_token_hash != token_helpers.sha256_hex(raw_token):
            raise AppError("not_found", "Export not found.", 404)
    elif archive.space_id is not None:
        ctx = await caps.load_space_context(session, actor, archive.space_id)
        if not caps.can_export(ctx, archive.kind.value):
            raise AppError("forbidden", "You may not download this export.", 403)
    else:
        if not isinstance(actor, UserActor) or actor.user_id != archive.requested_by:
            raise AppError("not_found", "Export not found.", 404)
    storage = get_storage()
    return await storage.presign_get(_export_key(archive), ttl_seconds=15 * 60)


async def mint_share_link(session: AsyncSession, actor, archive_id: UUID) -> str:
    from app.config import get_settings
    from app.modules.permissions import capabilities as caps

    archive = await session.get(Archive, archive_id)
    if archive is None or archive.status != ArchiveStatus.succeeded:
        raise AppError("not_found", "Export not found.", 404)
    if archive.space_id is not None:
        ctx = await caps.load_space_context(session, actor, archive.space_id)
        if not caps.can_export(ctx, archive.kind.value):
            raise AppError("forbidden", "You may not share this export.", 403)
    elif not isinstance(actor, UserActor) or actor.user_id != archive.requested_by:
        raise AppError("not_found", "Export not found.", 404)
    raw = secrets.token_hex(32)
    archive.download_token_hash = token_helpers.sha256_hex(raw)
    await session.flush()
    base = get_settings().frontend_base_url.rstrip("/")
    return f"{base}/a/{archive.id}?t={raw}"


async def request_personal_export(session: AsyncSession, user_id: UUID,
                                  jobs: JobRunner) -> Archive:
    archive = Archive(
        space_id=None, requested_by=user_id, kind=ArchiveKind.data_export,
        status=ArchiveStatus.queued, idempotency_key=f"me-export:{user_id}:{uuid.uuid4().hex}")
    session.add(archive)
    await session.flush()
    await jobs.enqueue("build_archive", {"archive_id": str(archive.id)},
                       idempotency_key=archive.idempotency_key)
    return archive


async def list_personal_exports(session: AsyncSession, user_id: UUID) -> list[Archive]:
    result = await session.execute(
        select(Archive).where(Archive.space_id.is_(None), Archive.requested_by == user_id)
        .order_by(Archive.created_at.desc()).limit(20))
    return list(result.scalars().all())


async def close_account(session: AsyncSession, user_id: UUID, confirm_email: str) -> None:
    from sqlalchemy import update

    user = await session.get(User, user_id)
    assert user is not None
    if token_helpers.normalize_email(confirm_email) != user.email.lower():
        raise AppError("validation_error", "Confirmation email does not match.", 422)
    owned = await session.execute(select(Space).where(
        Space.owner_id == user_id, Space.deleted_at.is_(None)))
    blocking = list(owned.scalars().all())
    if blocking:
        raise AppError(
            "conflict", "Transfer or delete your spaces before closing your account.", 409,
            details={"spaces": [{"id": str(space.id), "title": space.title}
                                for space in blocking]})
    user.deleted_at = _utcnow()
    await session.execute(update(UserSession).where(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
    ).values(revoked_at=_utcnow()))
    await session.flush()
    logger.info("account closed user=%s", user_id)


async def purge_account(session: AsyncSession, user_id: UUID, confirm_email: str,
                        jobs: JobRunner) -> None:
    """Full erasure in one step (close + scrub run inside the purge job).

    Kept separate from soft close so owners can recover within the grace
    window via support; purge itself is immediate and irreversible.
    """
    user = await session.get(User, user_id)
    assert user is not None
    if token_helpers.normalize_email(confirm_email) != user.email.lower():
        raise AppError("validation_error", "Confirmation email does not match.", 422)
    owned = await session.execute(select(Space).where(
        Space.owner_id == user_id, Space.deleted_at.is_(None)))
    blocking = list(owned.scalars().all())
    if blocking:
        raise AppError(
            "conflict", "Transfer or delete your spaces before purging your account.", 409,
            details={"spaces": [{"id": str(space.id), "title": space.title}
                                for space in blocking]})
    await jobs.enqueue("purge_user", {"user_id": str(user_id)},
                       idempotency_key=f"purge-user:{user_id}")
    logger.info("account purge requested user=%s", user_id)

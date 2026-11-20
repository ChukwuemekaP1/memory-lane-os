"""Archive executors: export builders + account purge."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.logging import get_logger
from app.models.archives import Archive
from app.models.contributions import Contribution, ContributionAttachment, MediaAsset
from app.models.enums import ArchiveKind, ArchiveStatus, ContributionStatus, MediaKind, MediaStatus
from app.models.interactions import ModerationRecord, Reaction, Reply
from app.models.scheduling import Notification, ScheduledEvent
from app.models.spaces import GuestAccessToken, Invitation, Space, SpaceMembership
from app.models.users import OtpChallenge, User, UserSession
from app.modules.archives.service import EXPORT_TTL_DAYS
from app.services.jobs import job

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@job("build_archive")
async def build_archive_job(payload: dict[str, Any]) -> None:
    from app import db

    try:
        archive_id = UUID(payload["archive_id"])
    except (KeyError, ValueError):
        raise AppError("internal_error", "build_archive needs archive_id.", 500) from None
    async with db.session_scope() as session:
        archive = await session.get(Archive, archive_id)
        if archive is None or archive.status not in (ArchiveStatus.queued,
                                                     ArchiveStatus.running):
            return
        archive.status = ArchiveStatus.running
        await session.flush()
    try:
        key = await _build(archive_id)
    except AppError as exc:
        await _archive_failed(archive_id, exc.message)
        return
    except Exception:
        logger.exception("build_archive crashed id=%s", archive_id)
        await _archive_failed(archive_id, "Export failed unexpectedly.")
        return
    async with _session() as session:
        archive = await session.get(Archive, archive_id)
        assert archive is not None
        from datetime import timedelta as _td

        archive.status = ArchiveStatus.succeeded
        archive.expires_at = _utcnow() + _td(days=EXPORT_TTL_DAYS)
        await session.flush()
        if archive.requested_by is not None:
            requester = await session.get(User, archive.requested_by)
            if requester is not None and requester.deleted_at is None:
                from app.services.jobs import get_job_runner

                await get_job_runner().enqueue(
                    "send_email",
                    {"to": requester.email,
                     "subject": "Your export is ready",
                     "template": "export_ready_v1",
                     "text_body": f"Your {archive.kind.value} export is ready to download."},
                    idempotency_key=f"export-ready:{archive.id}")
    logger.info("archive built id=%s key=%s", archive_id, key)


def _session():  # type: ignore[no-untyped-def]
    from app import db

    return db.session_scope()


async def _archive_failed(archive_id: UUID, reason: str) -> None:
    async with _session() as session:
        archive = await session.get(Archive, archive_id)
        if archive is None:
            return
        archive.status = ArchiveStatus.dead
        archive.last_error = reason[:500]
        await session.flush()


async def _build(archive_id: UUID) -> str:
    from app import db
    from app.modules.archives.builders import build_memory_book_pdf, build_zip

    async with db.session_scope() as session:
        archive = await session.get(Archive, archive_id)
        assert archive is not None
        kind = archive.kind
        include_private = True
        if archive.space_id is not None:
            space = await session.get(Space, archive.space_id)
            include_private = space is not None and archive.requested_by == space.owner_id
        if kind == ArchiveKind.data_export and archive.space_id is None:
            files = await _personal_data_files(session, archive)
            blob = build_zip(files)
        elif kind == ArchiveKind.data_export:
            assert archive.space_id is not None
            files = await _space_data_files(session, archive.space_id, include_private)
            files["manifest.json"] = _manifest_bytes(archive, files)
            blob = build_zip(files)
        elif kind == ArchiveKind.full_zip:
            assert archive.space_id is not None
            files = await _space_data_files(session, archive.space_id, include_private)
            files.update(await _original_files(session, archive.space_id, include_private))
            files["manifest.json"] = _manifest_bytes(archive, files)
            blob = build_zip(files)
        elif kind == ArchiveKind.book_pdf:
            assert archive.space_id is not None
            blob, report = await _book_pdf(session, archive, include_private)
            logger.info("book built id=%s report=%s", archive_id, report)
        elif kind == ArchiveKind.film_mp4:
            assert archive.space_id is not None
            blob = await _slideshow_film(session, archive, include_private)
        else:
            raise AppError("internal_error", f"Unsupported export kind: {kind}.", 500)
        from app.services.storage import get_storage

        key = _export_key_for(archive)
        mime = {"zip": "application/zip", "pdf": "application/pdf",
                "mp4": "video/mp4"}[key.rsplit(".", 1)[-1]]
        await get_storage().write_bytes(key, blob, mime)
        return key


def _export_key_for(archive: Archive) -> str:
    ext = {"full_zip": "zip", "book_pdf": "pdf", "film_mp4": "mp4",
           "data_export": "zip"}[archive.kind.value]
    scope = str(archive.space_id) if archive.space_id else f"user/{archive.requested_by}"
    return f"exports/{scope}/{archive.id}.{ext}"


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None


async def _space_rows(session: AsyncSession, space_id: UUID):
    contributions = list((await session.execute(
        select(Contribution).where(Contribution.space_id == space_id,
                                   Contribution.deleted_at.is_(None))
        .order_by(Contribution.created_at))).scalars().all())
    assets = list((await session.execute(
        select(MediaAsset).where(MediaAsset.space_id == space_id,
                                 MediaAsset.deleted_at.is_(None)))).scalars().all())
    return contributions, assets


def _contribution_dict(item: Contribution) -> dict:
    return {"id": str(item.id), "kind": item.kind.value, "body": item.body,
            "guest_name": item.guest_name, "author_snapshot": item.author_snapshot,
            "status": item.status.value, "anonymous": item.is_anonymous,
            "private_to_owner": item.is_private_to_owner,
            "taken_at": _iso(item.taken_at), "created_at": _iso(item.created_at),
            "categories": item.ai_categories}


async def _space_data_files(session: AsyncSession, space_id: UUID,
                            include_private: bool) -> dict[str, bytes]:
    space = await session.get(Space, space_id)
    assert space is not None
    contributions, assets = await _space_rows(session, space_id)
    if not include_private:
        contributions = [c for c in contributions if not c.is_private_to_owner]
    replies = list((await session.execute(
        select(Reply).where(Reply.contribution_id.in_([c.id for c in contributions] or [None]),
                            Reply.deleted_at.is_(None)))).scalars().all())
    reactions = list((await session.execute(
        select(Reaction).where(Reaction.contribution_id.in_(
            [c.id for c in contributions] or [None])))).scalars().all())
    payload = {
        "space": {"id": str(space.id), "title": space.title,
                  "description": space.description, "kind": space.kind,
                  "occasion": space.occasion, "visibility": space.visibility.value,
                  "event_date": str(space.event_date) if space.event_date else None,
                  "timezone": space.timezone, "created_at": _iso(space.created_at)},
        "contributions": [_contribution_dict(item) for item in contributions],
        "replies": [{"id": str(reply.id), "contribution_id": str(reply.contribution_id),
                     "guest_name": reply.guest_name, "body": reply.body,
                     "created_at": _iso(reply.created_at)} for reply in replies],
        "reactions": [{"contribution_id": str(reaction.contribution_id),
                       "emoji": reaction.emoji} for reaction in reactions],
        "assets": [{"id": str(asset.id), "kind": asset.kind.value,
                    "mime": asset.original_mime, "bytes": asset.original_bytes,
                    "key": asset.original_key, "sha256": asset.original_sha256,
                    "width": asset.width, "height": asset.height,
                    "duration_ms": asset.duration_ms, "status": asset.status.value}
                   for asset in assets],
    }
    return {"data.json": json.dumps(payload, indent=2).encode()}


async def _original_files(session: AsyncSession, space_id: UUID,
                          include_private: bool = True) -> dict[str, bytes]:
    from app.services.storage import get_storage

    storage = get_storage()
    _, assets = await _space_rows(session, space_id)
    hidden_assets: set[UUID] = set()
    if not include_private:
        rows = (await session.execute(
            select(ContributionAttachment.asset_id, Contribution.is_private_to_owner)
            .join(Contribution,
                  Contribution.id == ContributionAttachment.contribution_id)
            .where(Contribution.space_id == space_id))).all()
        by_asset: dict[UUID, list[bool]] = {}
        for asset_id, private in rows:
            by_asset.setdefault(asset_id, []).append(bool(private))
        hidden_assets = {asset_id for asset_id, flags in by_asset.items() if all(flags)}
    files: dict[str, bytes] = {}
    for asset in assets:
        if asset.id in hidden_assets:
            continue
        try:
            data = await storage.read_bytes(asset.original_key)
        except Exception:
            logger.warning("export missing bytes key=%s", asset.original_key)
            continue
        suffix = asset.original_key.rsplit("/", 1)[-1]
        files[f"originals/{asset.id}-{suffix}"] = data
    return files


def _manifest_bytes(archive: Archive, files: dict[str, bytes]) -> bytes:
    manifest = {"archive_id": str(archive.id), "kind": archive.kind.value,
                "exported_at": _utcnow().isoformat(), "files": sorted(files),
                "total_bytes": sum(len(data) for data in files.values()),
                "note": "Originals preserved bit-for-bit; see data.json for context."}
    return json.dumps(manifest, indent=2).encode()


async def _personal_data_files(session: AsyncSession, archive: Archive) -> dict[str, bytes]:
    assert archive.requested_by is not None
    user = await session.get(User, archive.requested_by)
    assert user is not None
    spaces = list((await session.execute(
        select(Space).where(Space.owner_id == user.id))).scalars().all())
    files = {"account.json": json.dumps(
        {"email": user.email, "display_name": user.display_name,
         "created_at": _iso(user.created_at)}).encode()}
    for space in spaces:
        for name, data in (await _space_data_files(session, space.id,
                                                   include_private=True)).items():
            files[f"spaces/{space.id}/{name}"] = data
    return files


async def _book_pdf(session: AsyncSession, archive: Archive,
                    include_private: bool) -> tuple[bytes, dict]:
    assert archive.space_id is not None
    from app.modules.archives.builders import build_memory_book_pdf
    from app.services.storage import get_storage

    space = await session.get(Space, archive.space_id)
    assert space is not None
    contributions, _ = await _space_rows(session, archive.space_id)
    visible = [c for c in contributions
               if c.status == ContributionStatus.visible
               and (include_private or not c.is_private_to_owner)]
    storage = get_storage()
    entries: list[dict] = []
    for item in visible:
        if item.body:
            name = item.guest_name or item.author_snapshot or "Someone"
            entries.append({"title": name, "text": item.body})
        attachments = (await session.execute(
            select(ContributionAttachment, MediaAsset)
            .join(MediaAsset, MediaAsset.id == ContributionAttachment.asset_id)
            .where(ContributionAttachment.contribution_id == item.id))).all()
        for link, asset in attachments:
            if asset.original_mime == "image/jpeg" and asset.status == MediaStatus.ready:
                try:
                    entries.append({"image_jpeg": await storage.read_bytes(asset.original_key),
                                    "caption": link.caption or ""})
                except Exception:
                    logger.warning("book missing bytes key=%s", asset.original_key)
    return build_memory_book_pdf(space.title, entries)


async def _slideshow_film(session: AsyncSession, archive: Archive,
                          include_private: bool) -> bytes:
    import tempfile
    from pathlib import Path

    assert archive.space_id is not None
    from app.services.ffmpeg import run_ffmpeg
    from app.services.storage import get_storage

    contributions, assets = await _space_rows(session, archive.space_id)
    eligible = {c.id for c in contributions
                if c.status == ContributionStatus.visible
                and (include_private or not c.is_private_to_owner)}
    linked = (await session.execute(
        select(ContributionAttachment.asset_id).where(
            ContributionAttachment.contribution_id.in_(eligible or [None])))).scalars().all()
    allowed = set(linked)
    images = [a for a in assets
              if a.id in allowed and a.kind == MediaKind.image and a.status == MediaStatus.ready]
    if not images:
        raise AppError("conflict", "No finished photos to build a film from.", 409)
    storage = get_storage()
    with tempfile.TemporaryDirectory(prefix="ml-export-film-") as tmp:
        workdir = Path(tmp)
        segments = []
        for index, asset in enumerate(images[:60]):
            src = workdir / f"img-{index}.bin"
            src.write_bytes(await storage.read_bytes(asset.original_key))
            out = workdir / f"seg-{index}.mp4"
            await run_ffmpeg(["-loop", "1", "-t", "3", "-i", str(src),
                              "-vf", "scale=1280:-2,format=yuv420p", "-c:v", "libx264",
                              "-preset", "veryfast", "-an", str(out)], "slideshow segment")
            segments.append(out)
        concat = workdir / "concat.txt"
        concat.write_text("".join(f"file '{segment}'\n" for segment in segments))
        final = workdir / "film.mp4"
        await run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat),
                          "-c", "copy", str(final)], "slideshow cut")
        return final.read_bytes()


@job("purge_user")
async def purge_user_job(payload: dict) -> None:
    """Scrub a closed account: PII removed, content tombstoned, financial
    rows retained (legal evidence) against the pseudonymous id."""
    from app import db

    try:
        user_id = UUID(payload["user_id"])
    except (KeyError, ValueError):
        raise AppError("internal_error", "purge_user needs user_id.", 500) from None
    scrub_email = f"deleted-{user_id.hex[:8]}@deleted.local"
    async with db.session_scope() as session:
        user = await session.get(User, user_id)
        if user is None or user.email == scrub_email:
            return  # nothing to do (idempotent)
        email = user.email
        user.email = scrub_email
        user.display_name = "Deleted member"
        user.deleted_at = _utcnow()
        user.email_verified_at = None
        user.locale = "en"
        user.marketing_opt_in = False
        user.digest_enabled = False
        user.reminder_enabled = False
        await session.execute(delete(UserSession).where(UserSession.user_id == user_id))
        await session.execute(delete(OtpChallenge).where(OtpChallenge.email == email))
        await session.execute(delete(SpaceMembership).where(SpaceMembership.user_id == user_id))
        await session.execute(delete(Reaction).where(Reaction.reactor_user_id == user_id))
        await session.execute(
            update(Contribution)
            .where(Contribution.author_user_id == user_id)
            .values(author_user_id=None, author_snapshot="Deleted member", guest_name=None))
        await session.execute(
            update(Reply).where(Reply.author_user_id == user_id)
            .values(author_user_id=None, guest_name=None))
        await session.execute(
            update(GuestAccessToken).where(GuestAccessToken.created_by == user_id)
            .values(created_by=None, created_by_email=None))
        await session.execute(
            update(Invitation).where(Invitation.invited_by == user_id)
            .values(invited_by=None))
        await session.execute(
            update(ModerationRecord).where(ModerationRecord.acted_by == user_id)
            .values(acted_by=None))
        await session.execute(
            update(ScheduledEvent).where(ScheduledEvent.user_id == user_id)
            .values(status=ScheduledStatus.cancelled))
        await session.execute(
            update(Notification).where(Notification.user_id == user_id)
            .values(user_id=None, email="deleted@deleted.local"))
        from app.models.ai import AIGenerationJob

        await session.execute(
            update(AIGenerationJob).where(AIGenerationJob.requested_by == user_id)
            .values(requested_by=None, requested_by_email=None))
        await session.execute(
            update(Archive).where(Archive.requested_by == user_id)
            .values(requested_by=None))
        # payments + usage_records intentionally retained (financial evidence).
    logger.info("purged user=%s", user_id)

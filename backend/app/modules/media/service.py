"""Media service: presigned uploads, verification, view URLs, deletion."""

from __future__ import annotations

import mimetypes
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.logging import get_logger
from app.models.contributions import MediaAsset, MediaProcessingJob
from app.models.enums import JobStatus, MediaKind, MediaStatus
from app.modules.permissions.capabilities import SpaceContext
from app.services.jobs import JobRunner
from app.services.storage import Storage

logger = get_logger(__name__)

MIME_TO_KIND: dict[str, MediaKind] = {
    "image/jpeg": MediaKind.image, "image/png": MediaKind.image,
    "image/webp": MediaKind.image, "image/heic": MediaKind.image,
    "image/heif": MediaKind.image,
    "video/mp4": MediaKind.video, "video/quicktime": MediaKind.video,
    "video/webm": MediaKind.video,
    "audio/mpeg": MediaKind.audio, "audio/mp4": MediaKind.audio,
    "audio/x-m4a": MediaKind.audio, "audio/wav": MediaKind.audio,
    "audio/x-wav": MediaKind.audio, "audio/ogg": MediaKind.audio,
    "audio/webm": MediaKind.audio,
    "application/pdf": MediaKind.other,
}
KIND_CAPS = {
    MediaKind.image: 25 * 1024 * 1024,
    MediaKind.video: 2 * 1024 * 1024 * 1024,
    MediaKind.audio: 200 * 1024 * 1024,
    MediaKind.other: 50 * 1024 * 1024,
}
UPLOAD_URL_TTL = 15 * 60
VIEW_URL_TTL = 60 * 60


def _kind_for(mime: str, declared: str | None) -> MediaKind:
    kind = MIME_TO_KIND.get(mime.lower())
    if kind is None:
        raise AppError("unsupported_media", f"Files of type {mime} are not supported.", 415)
    if declared is not None and declared != kind.value:
        raise AppError("validation_error",
                       f"Declared kind '{declared}' does not match {mime}.", 422)
    return kind


def _check_quota(space, declared_bytes: int) -> None:
    if space.storage_used_bytes + declared_bytes > space.storage_quota_bytes:
        raise AppError(
            "quota_exceeded", "This space is out of storage.", 403,
            details={"limit": space.storage_quota_bytes, "used": space.storage_used_bytes},
        )


async def presign_upload(
    session: AsyncSession, ctx: SpaceContext, storage: Storage,
    mime: str, declared_bytes: int, declared_kind: str | None,
) -> tuple[MediaAsset, str]:
    from app.modules.permissions import capabilities as caps

    if not caps.can_post(ctx):
        if ctx.actor is None:
            raise AppError("unauthenticated", "Authentication required.", 401)
        raise AppError("forbidden", "You may not upload to this space.", 403)
    kind = _kind_for(mime, declared_kind)
    if declared_bytes > KIND_CAPS[kind]:
        raise AppError("payload_too_large",
                       f"{kind.value} files are limited to {KIND_CAPS[kind]} bytes.", 413)
    _check_quota(ctx.space, declared_bytes)

    asset = MediaAsset(
        space_id=ctx.space.id, uploader_user_id=ctx.user_id,
        guest_token_id=ctx.guest_token_id, kind=kind,
        original_key="", original_bytes=declared_bytes, original_mime=mime,
        original_sha256="", derivatives=[], status=MediaStatus.reserved,
    )
    session.add(asset)
    await session.flush()  # assign id for the key
    ext = mimetypes.guess_extension(mime.split(";")[0].strip()) or ".bin"
    asset.original_key = f"originals/{ctx.space.id}/{asset.id}{ext}"
    await session.flush()
    upload_url = await storage.presign_put(asset.original_key, mime, declared_bytes,
                                           UPLOAD_URL_TTL)
    logger.info("presigned upload space=%s kind=%s bytes=%d", ctx.space.id, kind.value,
                declared_bytes)
    return asset, upload_url


async def confirm_upload(
    session: AsyncSession, ctx: SpaceContext, storage: Storage, jobs: JobRunner,
    asset_id: UUID,
) -> tuple[MediaAsset, MediaProcessingJob]:
    asset = await session.get(MediaAsset, asset_id)
    if asset is None or asset.space_id != ctx.space.id or asset.deleted_at is not None:
        raise AppError("not_found", "Upload not found.", 404)
    if not _uploader_matches(ctx, asset):
        raise AppError("forbidden", "You may only confirm your own uploads.", 403)
    latest = await _latest_job(session, asset.id)
    if latest is not None and latest.status in (JobStatus.queued, JobStatus.running,
                                                JobStatus.succeeded):
        return asset, latest  # idempotent re-confirm; terminal success included
    if asset.status == MediaStatus.ready:
        assert latest is not None
        return asset, latest

    actual_size = await storage.size(asset.original_key)
    if actual_size is None:
        raise AppError("conflict", "Bytes have not arrived yet; upload first, then confirm.", 409)
    if actual_size != asset.original_bytes:
        raise AppError("conflict",
                       f"Uploaded size {actual_size} does not match reservation "
                       f"{asset.original_bytes}.", 409)
    first_confirm = asset.status == MediaStatus.reserved
    if first_confirm:
        if ctx.space.storage_used_bytes + asset.original_bytes > ctx.space.storage_quota_bytes:
            raise AppError("quota_exceeded", "This space is out of storage.", 403,
                           details={"limit": ctx.space.storage_quota_bytes,
                                    "used": ctx.space.storage_used_bytes})
        ctx.space.storage_used_bytes += asset.original_bytes
        asset.status = MediaStatus.uploaded
    else:  # retry after failure: requeue without double-counting quota
        asset.status = MediaStatus.uploaded
        asset.failure_reason = None
    version = 1 if latest is None else latest.attempts + 1
    job = MediaProcessingJob(asset_id=asset.id,
                             idempotency_key=f"{asset.id}:v{version}",
                             status=JobStatus.queued, attempts=0)
    session.add(job)
    await session.flush()
    await jobs.enqueue("process_media", {"asset_id": str(asset.id)},
                       idempotency_key=job.idempotency_key)
    logger.info("confirmed upload space=%s asset=%s retry=%s", ctx.space.id, asset.id,
                not first_confirm)
    return asset, job


def _uploader_matches(ctx: SpaceContext, asset: MediaAsset) -> bool:
    if ctx.user_id is not None and asset.uploader_user_id == ctx.user_id:
        return True
    if ctx.guest_token_id is not None and asset.guest_token_id == ctx.guest_token_id:
        return True
    return bool(ctx.is_staff)


async def _latest_job(session: AsyncSession, asset_id: UUID) -> MediaProcessingJob | None:
    result = await session.execute(
        select(MediaProcessingJob).where(MediaProcessingJob.asset_id == asset_id)
        .order_by(MediaProcessingJob.created_at.desc(), MediaProcessingJob.id.desc()).limit(1))
    return result.scalar_one_or_none()


async def get_job_status(
    session: AsyncSession, ctx: SpaceContext, job_id: UUID,
) -> tuple[MediaProcessingJob, MediaAsset]:
    job = await session.get(MediaProcessingJob, job_id)
    if job is None:
        raise AppError("not_found", "Job not found.", 404)
    asset = await session.get(MediaAsset, job.asset_id)
    if asset is None or asset.space_id != ctx.space.id:
        raise AppError("not_found", "Job not found.", 404)
    if not _uploader_matches(ctx, asset):
        raise AppError("forbidden", "Not your upload.", 403)
    return job, asset


async def asset_view_urls(ctx: SpaceContext, asset: MediaAsset) -> dict:
    """Signed view URLs: derivatives for viewers, original for staff/own."""
    from app.modules.permissions import capabilities as caps
    from app.services.storage import get_storage

    storage = get_storage()
    rendered: dict = {"derivatives": {}}
    for rendition in asset.derivatives or []:
        label = rendition.get("label", "file")
        rendered["derivatives"][label] = await storage.presign_get(rendition["key"],
                                                                   VIEW_URL_TTL)
    if caps.can_view_original(ctx, asset.uploader_user_id, asset.guest_token_id):
        rendered["original"] = await storage.presign_get(asset.original_key, VIEW_URL_TTL)
    return rendered


async def download_url(
    session: AsyncSession, ctx: SpaceContext, asset_id: UUID, derivative: str | None,
) -> str:
    from app.modules.permissions import capabilities as caps
    from app.services.storage import get_storage

    asset = await session.get(MediaAsset, asset_id)
    if asset is None or asset.space_id != ctx.space.id or asset.deleted_at is not None:
        raise AppError("not_found", "Media not found.", 404)
    storage = get_storage()
    if derivative:
        for rendition in asset.derivatives or []:
            if rendition.get("label") == derivative:
                return await storage.presign_get(rendition["key"], VIEW_URL_TTL)
        raise AppError("not_found", "Derivative not found.", 404)
    if not caps.can_view_original(ctx, asset.uploader_user_id, asset.guest_token_id):
        raise AppError("forbidden", "Originals are available to staff and uploaders.", 403)
    return await storage.presign_get(asset.original_key, VIEW_URL_TTL)


async def delete_asset(session: AsyncSession, ctx: SpaceContext, asset_id: UUID) -> None:
    from app.services.storage import get_storage

    asset = await session.get(MediaAsset, asset_id)
    if asset is None or asset.space_id != ctx.space.id or asset.deleted_at is not None:
        raise AppError("not_found", "Media not found.", 404)
    if not _uploader_matches(ctx, asset):
        raise AppError("forbidden", "You may only delete your own uploads.", 403)
    from datetime import datetime, timezone as _tz

    asset.deleted_at = datetime.now(_tz.utc)
    ctx.space.storage_used_bytes = max(0, ctx.space.storage_used_bytes - asset.original_bytes)
    storage = get_storage()
    await storage.delete(asset.original_key)
    for rendition in asset.derivatives or []:
        await storage.delete(rendition["key"])
    await session.flush()
    logger.info("deleted asset space=%s asset=%s", ctx.space.id, asset.id)


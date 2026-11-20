"""Media routes: presign, confirm, view, download, delete, job status."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import enforce_rate_limit, get_job_runner_dep, get_rate_limiter_dep, get_storage_dep
from app.errors import AppError, ok_payload
from app.modules.media import processing as _processing  # noqa: F401 (registers process_media)
from app.modules.media import service
from app.modules.media.schemas import ConfirmIn, PresignIn
from app.modules.permissions.actor import get_actor
from app.modules.permissions.capabilities import SpaceContext, load_space_context
from app.services.jobs import JobRunner
from app.services.ratelimit import RateLimiter
from app.services.storage import Storage

router = APIRouter(tags=["media"])


async def _ctx_for(
    space_id: UUID, request: Request, session: AsyncSession,
) -> SpaceContext:
    actor = await get_actor(request, session)
    return await load_space_context(session, actor, space_id)


def _actor_key(ctx: SpaceContext, request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    if ctx.user_id is not None:
        return f"user:{ctx.user_id}:{ip}"
    if ctx.guest_token_id is not None:
        return f"token:{ctx.guest_token_id}:{ip}"
    return f"anon:{ip}"


def _asset_out(asset) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": str(asset.id), "space_id": str(asset.space_id), "kind": asset.kind.value,
        "mime": asset.original_mime, "bytes": asset.original_bytes,
        "width": asset.width, "height": asset.height, "duration_ms": asset.duration_ms,
        "status": asset.status.value, "failure_reason": asset.failure_reason,
        "derivatives": asset.derivatives or [],
    }


@router.post("/media/presign", status_code=status.HTTP_201_CREATED)
async def presign(
    body: PresignIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter_dep)],
    storage: Annotated[Storage, Depends(get_storage_dep)],
) -> dict:
    ctx = await _ctx_for(body.space_id, request, session)
    await enforce_rate_limit(limiter, f"presign:{ctx.space.id}:{_actor_key(ctx, request)}",
                             60, 60)
    asset, upload_url = await service.presign_upload(
        session, ctx, storage, body.mime, body.bytes, body.kind)
    return ok_payload({**_asset_out(asset), "asset_id": str(asset.id),
                       "upload_url": upload_url})


@router.post("/media/confirm", status_code=status.HTTP_202_ACCEPTED)
async def confirm(
    body: ConfirmIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[Storage, Depends(get_storage_dep)],
    jobs: Annotated[JobRunner, Depends(get_job_runner_dep)],
) -> dict:
    from app.models.contributions import MediaAsset

    asset = await session.get(MediaAsset, body.asset_id)
    if asset is None:
        raise AppError("not_found", "Upload not found.", 404)
    ctx = await _ctx_for(asset.space_id, request, session)
    asset, job = await service.confirm_upload(session, ctx, storage, jobs, body.asset_id)
    return ok_payload({"asset": _asset_out(asset), "processing_job_id": str(job.id),
                       "job_status": job.status.value})


@router.get("/media/{asset_id}")
async def get_asset(
    asset_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models.contributions import MediaAsset

    asset = await session.get(MediaAsset, asset_id)
    if asset is None:
        raise AppError("not_found", "Media not found.", 404)
    ctx = await _ctx_for(asset.space_id, request, session)
    if asset.deleted_at is not None:
        raise AppError("not_found", "Media not found.", 404)
    return ok_payload({**_asset_out(asset),
                       "urls": await service.asset_view_urls(ctx, asset)})


@router.get("/media/{asset_id}/download")
async def download_asset(
    asset_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    derivative: str | None = Query(default=None, max_length=40),
):
    from app.models.contributions import MediaAsset

    asset = await session.get(MediaAsset, asset_id)
    if asset is None:
        raise AppError("not_found", "Media not found.", 404)
    ctx = await _ctx_for(asset.space_id, request, session)
    url = await service.download_url(session, ctx, asset_id, derivative)
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


@router.delete("/media/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    from app.models.contributions import MediaAsset

    asset = await session.get(MediaAsset, asset_id)
    if asset is None:
        raise AppError("not_found", "Media not found.", 404)
    ctx = await _ctx_for(asset.space_id, request, session)
    await service.delete_asset(session, ctx, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/media/jobs/{job_id}")
async def get_job(
    job_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models.contributions import MediaAsset, MediaProcessingJob

    job = await session.get(MediaProcessingJob, job_id)
    if job is None:
        raise AppError("not_found", "Job not found.", 404)
    asset = await session.get(MediaAsset, job.asset_id)
    if asset is None:
        raise AppError("not_found", "Job not found.", 404)
    ctx = await _ctx_for(asset.space_id, request, session)
    job, asset = await service.get_job_status(session, ctx, job_id)
    return ok_payload({"job_id": str(job.id), "status": job.status.value,
                       "attempts": job.attempts, "last_error": job.last_error,
                       "asset": _asset_out(asset)})

"""Studio routes: jobs, assets, quota (API_SPECIFICATION Section 11)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import SettingsDep, get_job_runner_dep
from app.errors import ok_payload
from app.modules.permissions.actor import get_actor
from app.modules.permissions.capabilities import SpaceContext, load_space_context
from app.modules.studio import jobs as _jobs  # noqa: F401 (registers ai_run)
from app.modules.studio import service
from app.modules.studio.schemas import AIAssetPatchIn, AIJobCreateIn
from app.services.ai.quota import quota_status
from app.services.jobs import JobRunner

router = APIRouter(tags=["studio"])


async def _ctx(
    space_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SpaceContext:
    actor = await get_actor(request, session)
    return await load_space_context(session, actor, space_id)

SpaceCtx = Annotated[SpaceContext, Depends(_ctx)]


def _job_out(job) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": str(job.id), "kind": job.kind.value, "status": job.status.value,
        "provider": job.provider, "model": job.model,
        "attempts": job.attempts, "quota_reserved": job.quota_reserved,
        "input_tokens": job.input_tokens, "output_tokens": job.output_tokens,
        "cost_usd": float(job.cost_usd) if job.cost_usd is not None else None,
        "last_error": job.last_error,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def _asset_out(asset) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": str(asset.id), "job_id": str(asset.job_id), "kind": asset.kind.value,
        "title": asset.title, "text_body": asset.text_body,
        "asset_id": str(asset.asset_id) if asset.asset_id else None,
        "edit_list": asset.edit_list, "is_promoted": asset.is_promoted,
        "is_ai_labeled": asset.is_ai_labeled,
        "created_at": asset.created_at.isoformat(),
    }


@router.post("/spaces/{space_id}/ai/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    body: AIJobCreateIn,
    ctx: SpaceCtx,
    request: Request,
    settings: SettingsDep,
    session: Annotated[AsyncSession, Depends(get_session)],
    jobs: Annotated[JobRunner, Depends(get_job_runner_dep)],
) -> dict:
    key = body.idempotency_key or request.headers.get("idempotency-key")
    job = await service.enqueue_job(session, ctx, settings, jobs, body.kind, body.inputs, key)
    return ok_payload({**_job_out(job), "quota_reserved": job.quota_reserved})


@router.get("/spaces/{space_id}/ai/jobs")
async def list_jobs(
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
    kind: str | None = None,
    status: str | None = None,
) -> dict:
    rows = await service.list_jobs(session, ctx, kind, status)
    return ok_payload([_job_out(job) for job in rows])


@router.get("/ai/jobs/{job_id}")
async def get_job(
    job_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.errors import AppError
    from app.models.ai import AIGenerationJob

    job = await session.get(AIGenerationJob, job_id)
    if job is None:
        raise AppError("not_found", "Job not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, job.space_id)
    return ok_payload(_job_out(await service.get_job(session, ctx, job_id)))


@router.post("/ai/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.errors import AppError
    from app.models.ai import AIGenerationJob

    job = await session.get(AIGenerationJob, job_id)
    if job is None:
        raise AppError("not_found", "Job not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, job.space_id)
    return ok_payload(_job_out(await service.cancel_job(session, ctx, job_id)))


@router.get("/spaces/{space_id}/ai/assets")
async def list_assets(
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
    kind: str | None = None,
    promoted_only: bool = Query(default=False),
) -> dict:
    rows = await service.list_assets(session, ctx, kind, promoted_only)
    return ok_payload([_asset_out(asset) for asset in rows])


@router.patch("/ai/assets/{asset_id}")
async def patch_asset(
    asset_id: UUID,
    body: AIAssetPatchIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.errors import AppError
    from app.models.ai import AIGeneratedAsset

    asset = await session.get(AIGeneratedAsset, asset_id)
    if asset is None:
        raise AppError("not_found", "Asset not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, asset.space_id)
    return ok_payload(_asset_out(await service.patch_asset(
        session, ctx, asset_id, body.title, body.text_body)))


@router.post("/ai/assets/{asset_id}/promote")
async def promote_asset(
    asset_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    caption_target: dict | None = None,
) -> dict:
    from app.errors import AppError
    from app.models.ai import AIGeneratedAsset

    asset = await session.get(AIGeneratedAsset, asset_id)
    if asset is None:
        raise AppError("not_found", "Asset not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, asset.space_id)
    # Optional JSON body {"attachment_id": ..., "text": ...} writes one approved
    # caption onto an attachment (presentation metadata, owner-approved).
    return ok_payload(_asset_out(await service.promote_asset(
        session, ctx, asset_id, caption_target)))


@router.delete("/ai/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    from app.errors import AppError
    from app.models.ai import AIGeneratedAsset

    asset = await session.get(AIGeneratedAsset, asset_id)
    if asset is None:
        raise AppError("not_found", "Asset not found.", 404)
    actor = await get_actor(request, session)
    ctx = await load_space_context(session, actor, asset.space_id)
    await service.delete_asset(session, ctx, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/spaces/{space_id}/ai/quota")
async def get_quota(
    ctx: SpaceCtx,
    settings: SettingsDep,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models.archives import Subscription
    from app.models.enums import Plan
    from sqlalchemy import select

    from app.modules.permissions import capabilities as caps

    caps.require_staff(ctx)
    plan = Plan.free
    if ctx.is_owner and ctx.user_id is not None:
        row = await session.execute(select(Subscription.plan).where(
            Subscription.user_id == ctx.user_id,
            Subscription.status.in_(["active", "past_due"])))
        plan = row.scalar_one_or_none() or Plan.free
    assert ctx.user_id is not None
    return ok_payload(await quota_status(session, settings, ctx.user_id, plan))


@router.get("/spaces/{space_id}/ai/capabilities")
async def get_capabilities(
    ctx: SpaceCtx,
    settings: SettingsDep,
) -> dict:
    from app.modules.permissions import capabilities as caps

    caps.require_staff(ctx)
    has_key = settings.ai_provider == "fake" or bool(settings.openrouter_api_key)

    def _cap(model: str, enabled: bool = True, reason: str | None = None) -> dict:
        ok = has_key and enabled and bool(model)
        if not has_key:
            msg = "OPENROUTER_API_KEY is not configured on the server."
        elif not enabled:
            msg = reason or "This capability is disabled in server configuration."
        elif not model:
            msg = reason or "No compatible model is configured for this capability."
        else:
            msg = None
        return {"available": ok, "model": model or None, "reason": msg}

    return ok_payload({
        "provider": settings.ai_provider,
        "ai_opt_in": ctx.space.ai_opt_in,
        "capabilities": {
            "summary": _cap(settings.ai_text_model),
            "categorization": _cap(settings.ai_text_model),
            "letter": _cap(settings.ai_text_model),
            "book": _cap(settings.ai_text_model),
            "story_enhancement": _cap(settings.ai_text_model),
            "captions": _cap(settings.ai_vision_model),
            "transcription": _cap(
                settings.ai_audio_model,
                enabled=settings.ai_audio_supported or settings.ai_provider == "fake",
                reason="Audio transcription is disabled (set AI_AUDIO_SUPPORTED=true and a verified audio-capable model).",
            ),
            "image_generation": _cap(
                settings.ai_image_model or ("fake" if settings.ai_provider == "fake" else ""),
                reason="No image generation model configured (OPENROUTER_IMAGE_MODEL).",
            ),
            "highlight_film": _cap(settings.ai_text_model),
        },
    })

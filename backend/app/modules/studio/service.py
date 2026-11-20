"""Studio service: job lifecycle, privacy-safe input collection, assets."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import AppError
from app.logging import get_logger
from app.models.ai import AIGeneratedAsset, AIGenerationJob
from app.models.contributions import Contribution, MediaAsset
from app.models.enums import AIJobStatus, AIKind, ContributionStatus, MediaStatus, Plan
from app.modules.permissions.capabilities import SpaceContext
from app.services.ai.quota import check_ai_quota
from app.services.jobs import JobRunner

logger = get_logger(__name__)

ESTIMATES = {
    AIKind.transcription: 2000, AIKind.categorization: 3000, AIKind.captions: 1500,
    AIKind.summary: 4000, AIKind.letter: 2500, AIKind.book: 8000,
    AIKind.highlight_film: 3000, AIKind.image_generation: 3000,
    AIKind.story_enhancement: 2500,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_kind(value: str) -> AIKind:
    try:
        return AIKind(value)
    except ValueError:
        valid = ", ".join(k.value for k in AIKind)
        raise AppError("validation_error", f"Invalid kind. Expected one of: {valid}.", 422) from None


async def _owner_plan(session: AsyncSession, owner_id: UUID) -> Plan:
    from app.models.archives import Subscription

    result = await session.execute(
        select(Subscription.plan).where(
            Subscription.user_id == owner_id,
            Subscription.status.in_(["active", "past_due"])))
    plan = result.scalar_one_or_none()
    return plan if plan is not None else Plan.free


async def enqueue_job(
    session: AsyncSession, ctx: SpaceContext, settings: Settings, jobs: JobRunner,
    kind: str, inputs: dict, idempotency_key: str | None,
) -> AIGenerationJob:
    from app.modules.permissions import capabilities as caps

    if not (ctx.is_owner or ctx.is_collaborator):
        raise AppError("forbidden", "Only space staff may run AI Studio.", 403)
    if not ctx.space.ai_opt_in:
        raise AppError("forbidden", "AI is not enabled for this space.", 403)
    parsed = _parse_kind(kind)
    _validate_inputs(parsed, inputs)
    key = idempotency_key or uuid.uuid4().hex
    existing = await session.execute(
        select(AIGenerationJob).where(AIGenerationJob.idempotency_key == key))
    found = existing.scalar_one_or_none()
    if found is not None:
        if found.space_id != ctx.space.id:
            raise AppError("conflict", "Idempotency key already used.", 409)
        return found
    assert ctx.user_id is not None
    plan = await _owner_plan(session, ctx.space.owner_id)
    estimate = ESTIMATES[parsed]
    await check_ai_quota(session, settings, ctx.user_id, plan, estimate)
    job = AIGenerationJob(
        space_id=ctx.space.id, requested_by=ctx.user_id, kind=parsed, inputs=inputs,
        provider=settings.ai_provider, status=AIJobStatus.queued, attempts=0,
        idempotency_key=key, quota_reserved=estimate,
    )
    session.add(job)
    await session.flush()
    await jobs.enqueue("ai_run", {"job_id": str(job.id)}, idempotency_key=f"ai:{job.id}")
    logger.info("ai job enqueued space=%s kind=%s", ctx.space.id, parsed.value)
    return job


def _validate_inputs(kind: AIKind, inputs: dict) -> None:
    if not isinstance(inputs, dict):
        raise AppError("validation_error", "inputs must be an object.", 422)
    if kind == AIKind.transcription and not inputs.get("asset_ids"):
        raise AppError("validation_error", "transcription needs asset_ids.", 422)
    if kind == AIKind.captions and not inputs.get("asset_ids"):
        raise AppError("validation_error", "captions need asset_ids.", 422)
    if kind == AIKind.letter and not inputs.get("to"):
        raise AppError("validation_error", "letters need a recipient (to).", 422)
    if kind == AIKind.book and not inputs.get("title"):
        raise AppError("validation_error", "books need a title.", 422)
    if kind == AIKind.highlight_film and not inputs.get("asset_ids"):
        raise AppError("validation_error", "highlight films need asset_ids.", 422)
    if kind == AIKind.image_generation and not str(inputs.get("prompt", "")).strip():
        raise AppError("validation_error", "image_generation needs a non-empty prompt.", 422)


async def eligible_contributions(
    session: AsyncSession, ctx: SpaceContext, ids: list[str] | None, limit: int = 200,
) -> tuple[list[Contribution], dict]:
    """Visible, non-private, non-deleted contributions. Privacy is strict:
    private_to_owner, pending, hidden, and rejected items are NEVER AI inputs."""
    query = select(Contribution).where(
        Contribution.space_id == ctx.space.id, Contribution.deleted_at.is_(None),
        Contribution.status == ContributionStatus.visible,
        Contribution.is_private_to_owner.is_(False))
    if ids:
        try:
            parsed = [UUID(raw) for raw in ids]
        except ValueError:
            raise AppError("validation_error", "Invalid contribution id.", 422) from None
        query = query.where(Contribution.id.in_(parsed))
    query = query.order_by(Contribution.created_at).limit(limit + 1)
    rows = list((await session.execute(query)).scalars().all())
    skipped = 0
    if ids:
        skipped = len(ids) - len(rows)
    return rows[:limit], {"processed": len(rows[:limit]), "skipped_private": max(0, skipped)}


async def eligible_assets(
    session: AsyncSession, ctx: SpaceContext, ids: list[str], kinds: set[str] | None = None,
) -> list[MediaAsset]:
    try:
        parsed = [UUID(raw) for raw in ids]
    except ValueError:
        raise AppError("validation_error", "Invalid asset id.", 422) from None
    result = await session.execute(select(MediaAsset).where(MediaAsset.id.in_(parsed)))
    assets = list(result.scalars().all())
    if len(assets) != len(parsed):
        raise AppError("not_found", "An asset was not found.", 404)
    out = []
    for asset in assets:
        if asset.space_id != ctx.space.id or asset.deleted_at is not None:
            raise AppError("not_found", "An asset was not found.", 404)
        if asset.status != MediaStatus.ready:
            raise AppError("conflict", "All uploads must finish processing first.", 409)
        if kinds is not None and asset.kind.value not in kinds:
            raise AppError("validation_error", f"Asset {asset.id} has the wrong kind.", 422)
        out.append(asset)
    return out


async def get_job(session: AsyncSession, ctx: SpaceContext, job_id: UUID) -> AIGenerationJob:
    from app.modules.permissions import capabilities as caps

    job = await session.get(AIGenerationJob, job_id)
    if job is None or job.space_id != ctx.space.id:
        raise AppError("not_found", "Job not found.", 404)
    if not (ctx.is_owner or ctx.is_collaborator):
        raise AppError("forbidden", "Staff only.", 403)
    return job


async def list_jobs(session: AsyncSession, ctx: SpaceContext, kind: str | None,
                    status: str | None) -> list[AIGenerationJob]:
    from app.modules.permissions import capabilities as caps

    caps.require_staff(ctx)
    query = select(AIGenerationJob).where(AIGenerationJob.space_id == ctx.space.id)
    if kind:
        query = query.where(AIGenerationJob.kind == _parse_kind(kind))
    if status:
        try:
            query = query.where(AIGenerationJob.status == AIJobStatus(status))
        except ValueError:
            raise AppError("validation_error", "Invalid status.", 422) from None
    result = await session.execute(query.order_by(AIGenerationJob.created_at.desc()).limit(100))
    return list(result.scalars().all())


async def cancel_job(session: AsyncSession, ctx: SpaceContext, job_id: UUID) -> AIGenerationJob:
    job = await get_job(session, ctx, job_id)
    if job.status not in (AIJobStatus.queued, AIJobStatus.running):
        raise AppError("conflict", "Only queued or running jobs can be cancelled.", 409)
    job.status = AIJobStatus.cancelled
    job.quota_reserved = 0  # reservation released (see quota accounting)
    await session.flush()
    return job


async def list_assets(session: AsyncSession, ctx: SpaceContext, kind: str | None,
                      promoted_only: bool) -> list[AIGeneratedAsset]:
    from app.modules.permissions import capabilities as caps

    caps.require_staff(ctx)
    query = select(AIGeneratedAsset).where(
        AIGeneratedAsset.space_id == ctx.space.id,
        AIGeneratedAsset.deleted_at.is_(None))
    if kind:
        query = query.where(AIGeneratedAsset.kind == _parse_kind(kind))
    if promoted_only:
        query = query.where(AIGeneratedAsset.is_promoted.is_(True))
    result = await session.execute(query.order_by(AIGeneratedAsset.created_at.desc()).limit(100))
    return list(result.scalars().all())


async def _get_asset(session: AsyncSession, ctx: SpaceContext, asset_id: UUID) -> AIGeneratedAsset:
    from app.modules.permissions import capabilities as caps

    caps.require_staff(ctx)
    asset = await session.get(AIGeneratedAsset, asset_id)
    if asset is None or asset.space_id != ctx.space.id or asset.deleted_at is not None:
        raise AppError("not_found", "Asset not found.", 404)
    return asset


async def patch_asset(session: AsyncSession, ctx: SpaceContext, asset_id: UUID,
                      title: str | None, text_body: str | None) -> AIGeneratedAsset:
    asset = await _get_asset(session, ctx, asset_id)
    if title is not None:
        asset.title = title
    if text_body is not None:
        asset.text_body = text_body
    await session.flush()
    return asset


async def promote_asset(session: AsyncSession, ctx: SpaceContext, asset_id: UUID,
                        caption_target: dict | None = None) -> AIGeneratedAsset:
    """Approve an asset into the space. Captions may also write one attachment
    caption (presentation metadata, owner-approved)."""
    asset = await _get_asset(session, ctx, asset_id)
    asset.is_promoted = True
    asset.is_ai_labeled = True
    if caption_target:
        from app.models.contributions import ContributionAttachment

        attachment = await session.get(ContributionAttachment, caption_target.get("attachment_id"))
        if attachment is None:
            raise AppError("not_found", "Attachment not found.", 404)
        parent = await session.get(Contribution, attachment.contribution_id)
        if parent is None or parent.space_id != ctx.space.id:
            raise AppError("not_found", "Attachment not found.", 404)
        text = (caption_target.get("text") or "")[:500]
        if not text.strip():
            raise AppError("validation_error", "Caption text is required.", 422)
        attachment.caption = text.strip()
    await session.flush()
    return asset


async def delete_asset(session: AsyncSession, ctx: SpaceContext, asset_id: UUID) -> None:
    asset = await _get_asset(session, ctx, asset_id)
    asset.deleted_at = _utcnow()
    await session.flush()

"""AI quota accounting: monthly token budgets per plan (usage_records)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import AppError
from app.models.ai import AIGenerationJob
from app.models.archives import UsageRecord
from app.models.enums import AIJobStatus, Plan, UsageKind

AI_USAGE_KINDS = [UsageKind.ai_text, UsageKind.ai_vision, UsageKind.ai_transcription,
                  UsageKind.ai_film]


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def month_usage(session: AsyncSession, user_id: UUID) -> int:
    start = _month_start(datetime.now(timezone.utc))
    total = await session.scalar(select(func.coalesce(func.sum(UsageRecord.units), 0)).where(
        UsageRecord.user_id == user_id, UsageRecord.kind.in_(AI_USAGE_KINDS),
        UsageRecord.created_at >= start))
    return int(total or 0)


async def outstanding_reserved(session: AsyncSession, user_id: UUID) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(AIGenerationJob.quota_reserved), 0)).where(
            AIGenerationJob.requested_by == user_id,
            AIGenerationJob.status.in_([AIJobStatus.queued, AIJobStatus.running])))
    return int(total or 0)


def plan_cap(settings: Settings, plan: Plan) -> int:
    return settings.premium_monthly_ai_tokens if plan == Plan.premium else settings.free_monthly_ai_tokens


async def check_ai_quota(session: AsyncSession, settings: Settings, user_id: UUID, plan: Plan,
                         estimate_tokens: int) -> None:
    used = await month_usage(session, user_id)
    reserved = await outstanding_reserved(session, user_id)
    cap = plan_cap(settings, plan)
    if used + reserved + estimate_tokens > cap:
        raise AppError(
            "quota_exceeded",
            "Monthly AI budget exhausted. It resets on the 1st.", 403,
            details={"limit": cap, "used": used, "reserved": reserved},
        )


async def quota_status(session: AsyncSession, settings: Settings, user_id: UUID,
                       plan: Plan) -> dict:
    used = await month_usage(session, user_id)
    reserved = await outstanding_reserved(session, user_id)
    cap = plan_cap(settings, plan)
    now = datetime.now(timezone.utc)
    if now.month == 12:
        resets = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0,
                             second=0, microsecond=0)
    else:
        resets = now.replace(month=now.month + 1, day=1, hour=0, minute=0,
                             second=0, microsecond=0)
    return {"plan": plan.value, "limit": cap, "used": used, "reserved": reserved,
            "resets_at": resets.isoformat()}


async def record_usage(session: AsyncSession, user_id: UUID, space_id: UUID | None,
                       kind: UsageKind, units: int, ref_type: str, ref_id: UUID,
                       idempotency_key: str) -> None:
    session.add(UsageRecord(user_id=user_id, space_id=space_id, kind=kind, units=units,
                            ref_type=ref_type, ref_id=ref_id,
                            idempotency_key=idempotency_key))
    await session.flush()

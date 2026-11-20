"""Scheduling service: event CRUD + due-queue executor (ADR-008)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import AppError
from app.logging import get_logger
from app.models.contributions import Contribution
from app.models.enums import ContributionStatus, ScheduledKind, ScheduledStatus, SpaceVisibility
from app.models.scheduling import ScheduledEvent
from app.models.spaces import Space, SpaceMembership, SpaceSettings
from app.models.users import User
from app.modules.permissions.capabilities import SpaceContext
from app.services.jobs import JobRunner

logger = get_logger(__name__)

MAX_ATTEMPTS = 5
CLAIM_LEASE_MINUTES = 10
WORKER_ID = f"tick-{uuid.uuid4().hex[:8]}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_kind(value: str) -> ScheduledKind:
    try:
        return ScheduledKind(value)
    except ValueError:
        valid = ", ".join(k.value for k in ScheduledKind)
        raise AppError("validation_error", f"Invalid kind. Expected one of: {valid}.", 422) from None


def _require_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise AppError("validation_error", f"Invalid timezone: {value}.", 422) from None
    return value


def _as_utc(moment: datetime, zone: str) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)
    return moment.astimezone(timezone.utc)


async def list_events(session: AsyncSession, ctx: SpaceContext, kind: str | None,
                      status: str | None) -> list[ScheduledEvent]:
    from app.modules.permissions import capabilities as caps

    caps.require_staff(ctx)
    query = select(ScheduledEvent).where(ScheduledEvent.space_id == ctx.space.id)
    if kind:
        query = query.where(ScheduledEvent.kind == _parse_kind(kind))
    if status:
        try:
            query = query.where(ScheduledEvent.status == ScheduledStatus(status))
        except ValueError:
            raise AppError("validation_error", "Invalid status.", 422) from None
    result = await session.execute(query.order_by(ScheduledEvent.run_at).limit(200))
    return list(result.scalars().all())


async def create_event(
    session: AsyncSession, ctx: SpaceContext, kind: str, run_at: datetime,
    timezone_name: str | None, payload: dict,
) -> ScheduledEvent:
    from app.modules.permissions import capabilities as caps

    caps.require_staff(ctx)
    parsed = _parse_kind(kind)
    if parsed == ScheduledKind.digest:
        raise AppError("validation_error", "Digests are managed automatically.", 422)
    zone = _require_timezone(timezone_name or ctx.space.timezone)
    moment = _as_utc(run_at, zone)
    if moment <= _utcnow() + timedelta(minutes=5):
        raise AppError("validation_error", "run_at must be at least 5 minutes out.", 422)
    clean_payload = await _validate_payload(session, ctx, parsed, dict(payload or {}))
    if parsed == ScheduledKind.reveal:
        existing = await session.execute(select(ScheduledEvent).where(
            ScheduledEvent.space_id == ctx.space.id,
            ScheduledEvent.kind == ScheduledKind.reveal,
            ScheduledEvent.status == ScheduledStatus.scheduled))
        if existing.scalar_one_or_none() is not None:
            raise AppError("conflict", "This space already has a scheduled reveal.", 409)
    event = ScheduledEvent(
        space_id=ctx.space.id, kind=parsed, run_at=moment, timezone=zone,
        payload=clean_payload, status=ScheduledStatus.scheduled, attempts=0,
        idempotency_key=f"{parsed.value}:{ctx.space.id}:{uuid.uuid4().hex[:8]}",
    )
    session.add(event)
    await session.flush()
    if parsed == ScheduledKind.reveal:
        ctx.space.publish_at = moment
        if ctx.space.visibility == SpaceVisibility.link:
            ctx.space.visibility = SpaceVisibility.scheduled
        await session.flush()
    return event


async def _validate_payload(session: AsyncSession, ctx: SpaceContext, kind: ScheduledKind,
                            payload: dict) -> dict:
    if kind == ScheduledKind.future_letter:
        contribution_id = payload.get("contribution_id")
        if not contribution_id:
            raise AppError("validation_error", "future_letter needs contribution_id.", 422)
        try:
            item_id = UUID(str(contribution_id))
        except ValueError:
            raise AppError("validation_error", "Invalid contribution_id.", 422) from None
        item = await session.get(Contribution, item_id)
        if item is None or item.space_id != ctx.space.id:
            raise AppError("not_found", "Contribution not found.", 404)
        payload["contribution_id"] = str(item.id)
    if kind == ScheduledKind.capsule:
        ids = payload.get("contribution_ids", [])
        if not ids:
            raise AppError("validation_error", "capsule needs contribution_ids.", 422)
        try:
            parsed = [UUID(str(raw)) for raw in ids]
        except ValueError:
            raise AppError("validation_error", "Invalid contribution id.", 422) from None
        result = await session.execute(select(Contribution.id).where(
            Contribution.id.in_(parsed), Contribution.space_id == ctx.space.id))
        if len(list(result.scalars().all())) != len(parsed):
            raise AppError("not_found", "A capsule contribution was not found.", 404)
        payload["contribution_ids"] = [str(value) for value in parsed]
    return payload


async def cancel_event(session: AsyncSession, actor, event_id: UUID) -> ScheduledEvent:  # type: ignore[no-untyped-def]
    event, ctx = await _owned_event(session, actor, event_id)
    if event.status != ScheduledStatus.scheduled:
        raise AppError("conflict", "Only scheduled events can be cancelled.", 409)
    event.status = ScheduledStatus.cancelled
    if ctx is not None and event.kind == ScheduledKind.reveal \
            and ctx.space.publish_at == event.run_at:
        ctx.space.publish_at = None
    await session.flush()
    return event


async def reschedule_event(session: AsyncSession, actor, event_id: UUID,  # type: ignore[no-untyped-def]
                           run_at: datetime) -> ScheduledEvent:
    event, ctx = await _owned_event(session, actor, event_id)
    if event.status != ScheduledStatus.scheduled:
        raise AppError("conflict", "Only scheduled events can be rescheduled.", 409)
    moment = _as_utc(run_at, event.timezone)
    if moment <= _utcnow() + timedelta(minutes=5):
        raise AppError("validation_error", "run_at must be at least 5 minutes out.", 422)
    event.status = ScheduledStatus.cancelled
    await session.flush()
    clone = ScheduledEvent(
        space_id=event.space_id, user_id=event.user_id, kind=event.kind, run_at=moment,
        timezone=event.timezone, payload=event.payload, status=ScheduledStatus.scheduled,
        attempts=0, idempotency_key=f"{event.kind.value}:{event.space_id}:{uuid.uuid4().hex[:8]}",
    )
    session.add(clone)
    if ctx is not None and event.kind == ScheduledKind.reveal:
        ctx.space.publish_at = moment
    await session.flush()
    return clone


async def _owned_event(session: AsyncSession, actor, event_id: UUID):  # type: ignore[no-untyped-def]
    """Returns (event, ctx|None); 404 unless the actor owns/staffs the event."""
    from app.modules.permissions import capabilities as caps
    from app.modules.permissions.actor import UserActor

    event = await session.get(ScheduledEvent, event_id)
    if event is None:
        raise AppError("not_found", "Event not found.", 404)
    if event.space_id is not None:
        ctx = await caps.load_space_context(session, actor, event.space_id)
        caps.require_staff(ctx)
        return event, ctx
    if not isinstance(actor, UserActor) or actor.user_id != event.user_id:
        raise AppError("not_found", "Event not found.", 404)
    return event, None


async def my_reminders(session: AsyncSession, user_id: UUID, from_at: datetime | None,
                       to_at: datetime | None) -> list[ScheduledEvent]:
    owned_spaces = select(Space.id).where(Space.owner_id == user_id)
    query = select(ScheduledEvent).where(
        or_(ScheduledEvent.user_id == user_id,
            ScheduledEvent.space_id.in_(owned_spaces)),
        ScheduledEvent.status == ScheduledStatus.scheduled)
    if from_at is not None:
        query = query.where(ScheduledEvent.run_at >= from_at)
    if to_at is not None:
        query = query.where(ScheduledEvent.run_at <= to_at)
    result = await session.execute(query.order_by(ScheduledEvent.run_at).limit(200))
    return list(result.scalars().all())


async def update_prefs(session: AsyncSession, user_id: UUID, digest: bool | None,
                       reminders: bool | None) -> User:
    user = await session.get(User, user_id)
    assert user is not None
    if digest is not None:
        user.digest_enabled = digest
    if reminders is not None:
        user.reminder_enabled = reminders
    await session.flush()
    return user

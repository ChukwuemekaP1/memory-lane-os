"""Schedule executor: claim due events exactly once and run them.

Claim protocol (ADR-008): SELECT ... FOR UPDATE SKIP LOCKED over
`status=scheduled AND run_at <= now`, plus stale `claimed/running` rows whose
lease expired. Handlers are idempotent (reveal/publish flips, letter/capsule
status flips, emails keyed by event id).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.logging import get_logger
from app.models.contributions import Contribution
from app.models.enums import ContributionStatus, ScheduledKind, ScheduledStatus, SpaceVisibility
from app.models.scheduling import ScheduledEvent
from app.models.spaces import Space, SpaceMembership
from app.models.users import User
from app.services.jobs import JobRunner, job

logger = get_logger(__name__)

MAX_ATTEMPTS = 5
CLAIM_LEASE_MINUTES = 10
BATCH = 50


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@job("schedule_tick")
async def schedule_tick_job(payload: dict[str, Any]) -> None:
    await run_due_events(limit=int(payload.get("limit", BATCH)))


async def run_due_events(limit: int = BATCH) -> list[UUID]:
    """Claim and execute due events. Returns executed event ids (for tests)."""
    from app import db

    executed: list[UUID] = []
    async with db.session_scope() as session:
        events = await _claim_batch(session, limit)
        for event in events:
            event.status = ScheduledStatus.running
        await session.flush()
        ids = [event.id for event in events]
    for event_id in ids:
        try:
            await _execute_one(event_id)
            executed.append(event_id)
        except Exception:
            logger.exception("schedule event failed id=%s", event_id)
    return executed


async def _claim_batch(session: AsyncSession, limit: int) -> list[ScheduledEvent]:
    now = _utcnow()
    stale = now - timedelta(minutes=CLAIM_LEASE_MINUTES)
    result = await session.execute(
        select(ScheduledEvent)
        .where(
            or_(
                (ScheduledEvent.status == ScheduledStatus.scheduled)
                & (ScheduledEvent.run_at <= now),
                (ScheduledEvent.status.in_([ScheduledStatus.claimed, ScheduledStatus.running]))
                & (ScheduledEvent.claimed_at.is_not(None))
                & (ScheduledEvent.claimed_at < stale),
            )
        )
        .order_by(ScheduledEvent.run_at)
        .limit(limit)
        .with_for_update(skip_locked=True))
    events = list(result.scalars().all())
    for event in events:
        event.status = ScheduledStatus.claimed
        event.claimed_at = now
        event.claimed_by = WORKER_ID
    if events:
        await session.flush()
    return events


async def _execute_one(event_id: UUID) -> None:
    from app import db
    from app.services.jobs import get_job_runner

    async with db.session_scope() as session:
        event = await session.get(ScheduledEvent, event_id)
        if event is None or event.status not in (ScheduledStatus.claimed,
                                                 ScheduledStatus.running):
            return  # lost a race or was cancelled; exactly-once holds
        event.status = ScheduledStatus.running
        event.attempts += 1
        await session.flush()
        jobs = get_job_runner()
        try:
            handler = _HANDLERS[event.kind]
            await handler(session, event, jobs)
        except AppError as exc:
            await _fail(session, event, exc.message, retryable=False)
            return
        except Exception as exc:
            logger.exception("schedule handler crashed id=%s", event_id)
            await _fail(session, event, f"{type(exc).__name__}", retryable=True)
            return
        event.status = ScheduledStatus.done
        event.claimed_at = None
        await session.flush()
    logger.info("schedule event done id=%s kind=%s", event_id, event.kind.value)


async def _fail(session: AsyncSession, event: ScheduledEvent, reason: str,
                retryable: bool) -> None:
    if retryable and event.attempts < MAX_ATTEMPTS:
        event.status = ScheduledStatus.scheduled  # requeue with backoff via run_at
        event.run_at = _utcnow() + timedelta(minutes=2 ** min(event.attempts, 6))
        event.claimed_at = None
    else:
        event.status = ScheduledStatus.dead
    event.last_error = reason[:500]
    await session.flush()


async def _send(jobs: JobRunner, to: str, subject: str, template: str, text: str,
                key: str) -> None:
    await jobs.enqueue("send_email",
                       {"to": to, "subject": subject, "template": template,
                        "text_body": text},
                       idempotency_key=key)


async def _handle_reveal(session: AsyncSession, event: ScheduledEvent, jobs: JobRunner) -> None:
    assert event.space_id is not None
    space = await session.get(Space, event.space_id)
    if space is None or space.deleted_at is not None:
        return  # nothing to reveal; done
    if space.visibility != SpaceVisibility.scheduled:
        return  # published or unpublished manually; idempotent no-op
    space.visibility = SpaceVisibility.link
    space.publish_at = None
    await session.flush()
    owner = await session.get(User, space.owner_id)
    recipients = await _space_emails(session, space)
    for email in recipients:
        await _send(jobs, email, f"'{space.title}' is revealed!",
                    "reveal_v1",
                    f"The memory space '{space.title}' is now open for everyone with the link.",
                    f"reveal:{event.id}:{email}")
    if owner is not None and owner.email not in recipients:
        await _send(jobs, owner.email, f"'{space.title}' is revealed!", "reveal_v1",
                    f"Your memory space '{space.title}' is now open.",
                    f"reveal:{event.id}:{owner.email}")


async def _space_emails(session: AsyncSession, space: Space) -> list[str]:
    result = await session.execute(
        select(User.email).join(SpaceMembership, SpaceMembership.user_id == User.id).where(
            SpaceMembership.space_id == space.id, User.deleted_at.is_(None)))
    return [row for (row,) in result.all()]


async def _handle_reminder(session: AsyncSession, event: ScheduledEvent, jobs: JobRunner) -> None:
    if event.user_id is None:
        return
    user = await session.get(User, event.user_id)
    if user is None or user.deleted_at is not None or not user.reminder_enabled:
        return
    space_title = "your memory space"
    if event.space_id is not None:
        space = await session.get(Space, event.space_id)
        if space is not None:
            space_title = f"'{space.title}'"
    days = event.payload.get("days_before", "?")
    await _send(jobs, user.email, f"Reminder: {space_title} in {days} day(s)", "reminder_v1",
                f"A date you are tracking ({space_title}) is coming up in {days} day(s).",
                f"reminder:{event.id}")


async def _handle_future_letter(session: AsyncSession, event: ScheduledEvent,
                                jobs: JobRunner) -> None:
    contribution_id = event.payload.get("contribution_id")
    if not contribution_id:
        return
    item = await session.get(Contribution, UUID(str(contribution_id)))
    if item is None or item.deleted_at is not None:
        return
    if item.status == ContributionStatus.pending:
        item.status = ContributionStatus.visible
        await session.flush()
    space = await session.get(Space, item.space_id) if item.space_id else None
    owner = await session.get(User, space.owner_id) if space else None
    if owner is not None:
        await _send(jobs, owner.email, "A future letter was delivered", "letter_v1",
                    f"A scheduled letter is now visible in '{space.title if space else ''}'.",
                    f"letter:{event.id}")


async def _handle_capsule(session: AsyncSession, event: ScheduledEvent, jobs: JobRunner) -> None:
    ids = event.payload.get("contribution_ids", [])
    opened = 0
    for raw in ids:
        try:
            item = await session.get(Contribution, UUID(str(raw)))
        except ValueError:
            continue
        if item is None or item.deleted_at is not None:
            continue
        if event.space_id is not None and item.space_id != event.space_id:
            continue
        if item.status == ContributionStatus.pending:
            item.status = ContributionStatus.visible
            opened += 1
    await session.flush()
    if event.space_id is not None:
        space = await session.get(Space, event.space_id)
        owner = await session.get(User, space.owner_id) if space else None
        if owner is not None:
            await _send(jobs, owner.email, "A time capsule opened", "capsule_v1",
                        f"{opened} sealed memories are now visible"
                        f"{f' in {space.title!r}' if space else ''}.",
                        f"capsule:{event.id}")


async def _handle_digest(session: AsyncSession, event: ScheduledEvent, jobs: JobRunner) -> None:
    if event.user_id is None:
        return
    user = await session.get(User, event.user_id)
    if user is None or user.deleted_at is not None or not user.digest_enabled:
        return
    today = _utcnow().date()
    owned = select(Space.id).where(Space.owner_id == user.id, Space.deleted_at.is_(None))
    member = select(SpaceMembership.space_id).where(SpaceMembership.user_id == user.id)
    result = await session.execute(select(Contribution).where(
        Contribution.space_id.in_(owned.union(member)),
        Contribution.deleted_at.is_(None),
        Contribution.status == ContributionStatus.visible,
        func.extract("month", func.coalesce(Contribution.taken_at,
                                            Contribution.created_at)) == today.month,
        func.extract("day", func.coalesce(Contribution.taken_at,
                                          Contribution.created_at)) == today.day,
    ).order_by(Contribution.created_at).limit(10))
    items = [item for item in result.scalars().all()
             if item.created_at.date() < today and not item.is_private_to_owner]
    if not items:
        return  # quiet days send nothing
    lines = [f"- {(item.guest_name or item.author_snapshot or 'Someone')}: "
             f"{(item.body or '[memory]')[:140]}" for item in items]
    await _send(jobs, user.email, "On this day in your memories", "digest_v1",
                "On this day:\n" + "\n".join(lines), f"digest:{event.id}")


_HANDLERS = {
    ScheduledKind.reveal: _handle_reveal,
    ScheduledKind.reminder: _handle_reminder,
    ScheduledKind.future_letter: _handle_future_letter,
    ScheduledKind.capsule: _handle_capsule,
    ScheduledKind.digest: _handle_digest,
}

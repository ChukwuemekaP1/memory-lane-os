"""Scheduling routes: events, reminders, prefs (API_SPECIFICATION §12)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import ok_payload
from app.modules.permissions.actor import UserActor, get_actor, require_user
from app.modules.permissions.capabilities import SpaceContext, load_space_context
from app.modules.scheduling import service
from app.modules.scheduling.schemas import ReminderPrefsIn, RescheduleIn, ScheduleCreateIn

router = APIRouter(tags=["scheduling"])


async def _ctx(
    space_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SpaceContext:
    actor = await get_actor(request, session)
    return await load_space_context(session, actor, space_id)

SpaceCtx = Annotated[SpaceContext, Depends(_ctx)]


def _event_out(event) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": str(event.id),
        "space_id": str(event.space_id) if event.space_id else None,
        "kind": event.kind.value, "run_at": event.run_at.isoformat(),
        "timezone": event.timezone, "status": event.status.value,
        "attempts": event.attempts, "last_error": event.last_error,
    }


@router.get("/spaces/{space_id}/schedule")
async def list_events(
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
    kind: str | None = None,
    status: str | None = None,
) -> dict:
    rows = await service.list_events(session, ctx, kind, status)
    return ok_payload([_event_out(event) for event in rows])


@router.post("/spaces/{space_id}/schedule", status_code=201)
async def create_event(
    body: ScheduleCreateIn,
    ctx: SpaceCtx,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    event = await service.create_event(session, ctx, body.kind, body.run_at,
                                       body.timezone, body.payload)
    return ok_payload(_event_out(event))


@router.post("/schedule/{event_id}/reschedule")
async def reschedule_event(
    event_id: UUID,
    body: RescheduleIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    actor = await get_actor(request, session)
    event = await service.reschedule_event(session, actor, event_id, body.run_at)
    return ok_payload(_event_out(event))


@router.post("/schedule/{event_id}/cancel")
async def cancel_event(
    event_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    actor = await get_actor(request, session)
    event = await service.cancel_event(session, actor, event_id)
    return ok_payload(_event_out(event))


@router.get("/me/reminders")
async def my_reminders(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[UserActor, Depends(require_user)],
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
) -> dict:
    rows = await service.my_reminders(session, user.user_id, from_, to)
    return ok_payload([_event_out(event) for event in rows])


@router.patch("/me/reminder-prefs")
async def update_prefs(
    body: ReminderPrefsIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[UserActor, Depends(require_user)],
) -> dict:
    updated = await service.update_prefs(session, user.user_id, body.digest_enabled,
                                         body.reminder_enabled)
    return ok_payload({"digest_enabled": updated.digest_enabled,
                       "reminder_enabled": updated.reminder_enabled})

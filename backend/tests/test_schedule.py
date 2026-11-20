"""Scheduling + executor journeys (needs_pg; committed rows for the ticker)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.enums import ScheduledKind, ScheduledStatus
from app.models.scheduling import ScheduledEvent
from tests.helpers import create_space, login_as

pytestmark = pytest.mark.needs_pg


async def _space(committed_client, memory_services, **overrides):
    cookie = await login_as(committed_client, memory_services, "sched-owner@example.com")
    themes = await committed_client.get("/v1/themes", cookies={"ml_session": cookie})
    theme_id = next(t for t in themes.json()["data"] if t["plan_required"] == "free")["id"]
    data = await create_space(committed_client, cookie, theme_id, **overrides)
    return cookie, data["space"]["id"]


async def _insert_event(space_id, kind, run_at, timezone_name="Africa/Lagos", payload=None,
                        user_id=None, status="scheduled"):
    from app import db

    async with db.session_scope() as session:
        event = ScheduledEvent(
            space_id=uuid.UUID(space_id) if space_id else None,
            user_id=user_id, kind=ScheduledKind(kind), run_at=run_at, timezone=timezone_name,
            payload=payload or {}, status=ScheduledStatus(status), attempts=0,
            idempotency_key=f"test:{uuid.uuid4().hex}")
        session.add(event)
        await session.flush()
        return str(event.id)


async def test_reveal_executes_and_notifies(committed_client, memory_services):
    from app.models.spaces import Space
    from app.modules.scheduling.executor import run_due_events

    cookie, space_id = await _space(committed_client, memory_services, visibility="scheduled")
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    await _insert_event(space_id, "reveal", past)
    done = await run_due_events()
    assert len(done) == 1

    from app import db
    async with db.session_scope() as session:
        space = await session.get(Space, uuid.UUID(space_id))
        assert space.visibility.value == "link"
        assert space.publish_at is None
    mail = memory_services["mailer"].last_to("sched-owner@example.com")
    assert mail is not None and "revealed" in mail.subject.lower()
    # Second tick is a no-op (exactly once).
    assert await run_due_events() == []
    assert len([m for m in memory_services["mailer"].outbox if "revealed" in m.subject.lower()]) == 1


async def test_no_early_reveal(committed_client, memory_services):
    cookie, space_id = await _space(committed_client, memory_services, visibility="scheduled")
    stranger = await committed_client.get(f"/v1/spaces/{space_id}")
    assert stranger.status_code == 404
    owner = await committed_client.get(f"/v1/spaces/{space_id}", cookies={"ml_session": cookie})
    assert owner.status_code == 200
    assert owner.json()["data"]["preview"] is True


async def test_future_letter_delivery(committed_client, memory_services):
    from app import db
    from app.models.contributions import Contribution
    from app.modules.scheduling.executor import run_due_events

    cookie, space_id = await _space(committed_client, memory_services)
    posted = await committed_client.post(
        f"/v1/spaces/{space_id}/contributions",
        json={"kind": "future_letter", "body": "Open later", "guest_name": "Zed",
              "taken_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()},
        cookies={"ml_session": cookie})
    item_id = posted.json()["data"]["id"]
    # Force the letter event due now.
    async with db.session_scope() as session:
        events = (await session.execute(select(ScheduledEvent).where(
            ScheduledEvent.space_id == uuid.UUID(space_id),
            ScheduledEvent.kind == ScheduledKind.future_letter))).scalars().all()
        assert len(events) == 1
        events[0].run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await run_due_events()
    async with db.session_scope() as session:
        item = await session.get(Contribution, uuid.UUID(item_id))
        assert item.status.value == "visible"


async def test_capsule_opens_many(committed_client, memory_services):
    from app import db
    from app.models.contributions import Contribution
    from app.modules.scheduling.executor import run_due_events

    cookie, space_id = await _space(committed_client, memory_services,
                                    moderation_mode="pre")
    ids = []
    for idx in range(3):
        posted = await committed_client.post(
            f"/v1/spaces/{space_id}/contributions",
            json={"kind": "message", "body": f"Sealed {idx}", "guest_name": "Zed"},
            cookies={"ml_session": cookie})
        ids.append(posted.json()["data"]["id"])
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    await _insert_event(space_id, "capsule", past, payload={"contribution_ids": ids})
    await run_due_events()
    async with db.session_scope() as session:
        for item_id in ids:
            item = await session.get(Contribution, uuid.UUID(item_id))
            assert item.status.value == "visible"


async def test_reminder_requires_opt_in(committed_client, memory_services):
    from app import db
    from app.models.users import User
    from app.modules.scheduling.executor import run_due_events

    cookie, space_id = await _space(committed_client, memory_services)
    async with db.session_scope() as session:
        user = (await session.execute(
            select(User).where(User.email == "sched-owner@example.com"))).scalar_one()
        user.reminder_enabled = False
        user_id = user.id
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    await _insert_event(space_id, "reminder", past, payload={"days_before": 1},
                        user_id=user_id)
    await run_due_events()
    assert memory_services["mailer"].last_to("sched-owner@example.com") is None


async def test_timezone_due_logic(committed_client, memory_services):
    from app.modules.scheduling.executor import run_due_events

    cookie, space_id = await _space(committed_client, memory_services, visibility="scheduled")
    # Due an hour ago in UTC, expressed with a far-ahead zone: still fires (UTC rules).
    past_utc = datetime.now(timezone.utc) - timedelta(hours=1)
    await _insert_event(space_id, "reveal", past_utc, timezone_name="Pacific/Auckland")
    assert len(await run_due_events()) == 1
    # Future in UTC stays pending even if "today" in Auckland.
    future_utc = datetime.now(timezone.utc) + timedelta(hours=2)
    await _insert_event(space_id, "reveal", future_utc, timezone_name="Pacific/Auckland")
    assert await run_due_events() == []


async def test_cancel_and_reschedule_api(committed_client, memory_services):
    cookie, space_id = await _space(committed_client, memory_services)
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    created = await committed_client.post(
        f"/v1/spaces/{space_id}/schedule",
        json={"kind": "reminder", "run_at": future, "timezone": "Africa/Lagos",
              "payload": {"days_before": 2}},
        cookies={"ml_session": cookie})
    assert created.status_code == 201
    event_id = created.json()["data"]["id"]

    second_reveal = await committed_client.post(
        f"/v1/spaces/{space_id}/schedule",
        json={"kind": "reveal", "run_at": future}, cookies={"ml_session": cookie})
    assert second_reveal.status_code == 201
    duplicate = await committed_client.post(
        f"/v1/spaces/{space_id}/schedule",
        json={"kind": "reveal", "run_at": future}, cookies={"ml_session": cookie})
    assert duplicate.status_code == 409

    moved = await committed_client.post(
        f"/v1/schedule/{event_id}/reschedule",
        json={"run_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()},
        cookies={"ml_session": cookie})
    assert moved.status_code == 200
    assert moved.json()["data"]["id"] != event_id  # new version
    cancelled = await committed_client.post(f"/v1/schedule/{moved.json()['data']['id']}/cancel",
                                            cookies={"ml_session": cookie})
    assert cancelled.json()["data"]["status"] == "cancelled"
    again = await committed_client.post(f"/v1/schedule/{moved.json()['data']['id']}/cancel",
                                        cookies={"ml_session": cookie})
    assert again.status_code == 409


async def test_reminder_prefs_and_listing(committed_client, memory_services):
    cookie, space_id = await _space(committed_client, memory_services)
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    await committed_client.post(
        f"/v1/spaces/{space_id}/schedule",
        json={"kind": "reminder", "run_at": future}, cookies={"ml_session": cookie})
    mine = await committed_client.get("/v1/me/reminders", cookies={"ml_session": cookie})
    assert len(mine.json()["data"]) >= 1
    prefs = await committed_client.patch(
        "/v1/me/reminder-prefs", json={"digest_enabled": False},
        cookies={"ml_session": cookie})
    assert prefs.json()["data"]["digest_enabled"] is False

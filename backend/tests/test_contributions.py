"""Guest + member contribution journeys (needs_pg)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.scheduling import ScheduledEvent
from tests.helpers import create_space, login_as

pytestmark = pytest.mark.needs_pg


async def _guest_token(client, cookie, theme_id, **space_overrides):
    data = await create_space(client, cookie, theme_id, **space_overrides)
    raw = next(link for link in data["guest_links"]
               if link["token"]["role_cap"] == "contributor")["url"].split("guest=")[1]
    return data["space"]["id"], raw


async def test_guest_identified_post_and_confirm(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "c-owner@example.com")
    space_id, raw = await _guest_token(client, cookie, str(theme_row.id))
    response = await client.post(
        f"/v1/spaces/{space_id}/contributions",
        json={"kind": "message", "body": "Happy birthday!", "guest_name": "Zed"},
        headers={"Authorization": f"Bearer {raw}"})
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["body"] == "Happy birthday!"
    assert body["display_name"] == "Zed"
    assert body["status"] == "visible"


async def test_guest_anonymous_post_masked(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "a-owner@example.com")
    space_id, raw = await _guest_token(client, cookie, str(theme_row.id))
    posted = await client.post(
        f"/v1/spaces/{space_id}/contributions",
        json={"kind": "story", "body": "Secret santa story", "is_anonymous": True},
        headers={"Authorization": f"Bearer {raw}"})
    assert posted.status_code == 201
    item_id = posted.json()["data"]["id"]

    guest_view = await client.get(f"/v1/contributions/{item_id}",
                                  headers={"Authorization": f"Bearer {raw}"})
    assert guest_view.json()["data"]["display_name"] is None
    owner_view = await client.get(f"/v1/contributions/{item_id}",
                                  cookies={"ml_session": cookie})
    assert owner_view.json()["data"]["display_name"] is None  # no name was given
    assert owner_view.json()["data"]["is_anonymous"] is True


async def test_guest_requires_name_or_anonymous(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "n-owner@example.com")
    space_id, raw = await _guest_token(client, cookie, str(theme_row.id))
    response = await client.post(
        f"/v1/spaces/{space_id}/contributions",
        json={"kind": "message", "body": "Nameless"},
        headers={"Authorization": f"Bearer {raw}"})
    assert response.status_code == 422


async def test_private_note_owner_only(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "p-owner@example.com")
    data = await create_space(client, cookie, str(theme_row.id))
    space_id = data["space"]["id"]
    raw = next(link for link in data["guest_links"]
               if link["token"]["role_cap"] == "contributor")["url"].split("guest=")[1]
    viewer_raw = next(link for link in data["guest_links"]
                      if link["token"]["role_cap"] == "viewer")["url"].split("guest=")[1]

    posted = await client.post(
        f"/v1/spaces/{space_id}/contributions",
        json={"kind": "private_note", "body": "For your eyes only", "guest_name": "Zed"},
        headers={"Authorization": f"Bearer {raw}"})
    item_id = posted.json()["data"]["id"]
    assert posted.json()["data"]["is_private_to_owner"] is True

    assert (await client.get(
        f"/v1/contributions/{item_id}", cookies={"ml_session": cookie})).status_code == 200
    assert (await client.get(
        f"/v1/contributions/{item_id}",
        headers={"Authorization": f"Bearer {viewer_raw}"})).status_code == 404
    listed = await client.get(f"/v1/spaces/{space_id}/contributions",
                              headers={"Authorization": f"Bearer {viewer_raw}"})
    assert all(c["id"] != item_id for c in listed.json()["data"])


async def test_premoderation_approve_and_reject(client, memory_services, theme_row, session):
    cookie = await login_as(client, memory_services, "m-owner@example.com")
    space_id, raw = await _guest_token(client, cookie, str(theme_row.id),
                                       moderation_mode="pre")
    first = await client.post(
        f"/v1/spaces/{space_id}/contributions",
        json={"kind": "message", "body": "Pick me", "guest_name": "Zed"},
        headers={"Authorization": f"Bearer {raw}"})
    assert first.status_code == 202
    assert first.json()["data"]["status"] == "pending"
    first_id = first.json()["data"]["id"]
    second = await client.post(
        f"/v1/spaces/{space_id}/contributions",
        json={"kind": "message", "body": "Spam-ish", "guest_name": "Spammer"},
        headers={"Authorization": f"Bearer {raw}"})
    second_id = second.json()["data"]["id"]

    queue = await client.get(f"/v1/spaces/{space_id}/moderation/queue",
                             cookies={"ml_session": cookie})
    assert {c["id"] for c in queue.json()["data"]} == {first_id, second_id}

    approved = await client.post(f"/v1/moderation/contribution/{first_id}/approve",
                                 json={}, cookies={"ml_session": cookie})
    assert approved.json()["data"]["status"] == "visible"
    rejected = await client.post(f"/v1/moderation/contribution/{second_id}/reject",
                                 json={"reason": "Off-topic"},
                                 cookies={"ml_session": cookie})
    assert rejected.json()["data"]["status"] == "rejected"

    # Author sees own rejected item with the reason.
    mine = await client.get(f"/v1/contributions/{second_id}",
                            headers={"Authorization": f"Bearer {raw}"})
    assert mine.json()["data"]["rejection_reason"] == "Off-topic"
    log = await client.get(f"/v1/spaces/{space_id}/moderation/log",
                           cookies={"ml_session": cookie})
    assert len(log.json()["data"]) == 2


async def test_idempotent_replay(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "i-owner@example.com")
    space_id, raw = await _guest_token(client, cookie, str(theme_row.id))
    payload = {"kind": "message", "body": "Once only", "guest_name": "Zed"}
    headers = {"Authorization": f"Bearer {raw}", "Idempotency-Key": "key-123"}
    first = await client.post(f"/v1/spaces/{space_id}/contributions", json=payload,
                              headers=headers)
    second = await client.post(f"/v1/spaces/{space_id}/contributions", json=payload,
                               headers=headers)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert second.headers["Idempotent-Replayed"] == "true"


async def test_post_validation_errors(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "v-owner@example.com")
    space_id, raw = await _guest_token(client, cookie, str(theme_row.id))
    headers = {"Authorization": f"Bearer {raw}"}
    assert (await client.post(f"/v1/spaces/{space_id}/contributions",
                              json={"kind": "message", "guest_name": "Zed"},
                              headers=headers)).status_code == 422
    assert (await client.post(f"/v1/spaces/{space_id}/contributions",
                              json={"kind": "media", "guest_name": "Zed"},
                              headers=headers)).status_code == 422
    assert (await client.post(f"/v1/spaces/{space_id}/contributions",
                              json={"kind": "nope", "body": "x", "guest_name": "Zed"},
                              headers=headers)).status_code == 422


async def test_owner_only_policy_blocks_guests(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "o-owner@example.com")
    space_id, raw = await _guest_token(client, cookie, str(theme_row.id),
                                       contribution_policy="owner_only")
    denied = await client.post(
        f"/v1/spaces/{space_id}/contributions",
        json={"kind": "message", "body": "Let me in", "guest_name": "Zed"},
        headers={"Authorization": f"Bearer {raw}"})
    assert denied.status_code == 403


async def test_future_letter_schedules_delivery(client, memory_services, session, theme_row):
    cookie = await login_as(client, memory_services, "f-owner@example.com")
    space_id, raw = await _guest_token(client, cookie, str(theme_row.id))
    delivery = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    posted = await client.post(
        f"/v1/spaces/{space_id}/contributions",
        json={"kind": "future_letter", "body": "Open next year", "guest_name": "Zed",
              "taken_at": delivery},
        headers={"Authorization": f"Bearer {raw}"})
    assert posted.status_code == 201
    assert posted.json()["data"]["status"] == "pending"
    events = (await session.execute(select(ScheduledEvent).where(
        ScheduledEvent.space_id == uuid.UUID(space_id)))).scalars().all()
    letters = [e for e in events if e.kind.value == "future_letter"]
    assert len(letters) == 1
    assert letters[0].payload["contribution_id"] == posted.json()["data"]["id"]


async def test_edit_and_delete_own(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "e-owner@example.com")
    space_id, raw = await _guest_token(client, cookie, str(theme_row.id))
    headers = {"Authorization": f"Bearer {raw}"}
    posted = await client.post(f"/v1/spaces/{space_id}/contributions",
                               json={"kind": "message", "body": "Draft", "guest_name": "Zed"},
                               headers=headers)
    item_id = posted.json()["data"]["id"]
    edited = await client.patch(f"/v1/contributions/{item_id}", json={"body": "Final"},
                                headers=headers)
    assert edited.json()["data"]["body"] == "Final"
    forbidden = await client.patch(f"/v1/contributions/{item_id}", json={"body": "Hijack"},
                                   cookies={"ml_session": cookie})
    assert forbidden.status_code == 403  # staff never edit others' items
    deleted = await client.delete(f"/v1/contributions/{item_id}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/v1/contributions/{item_id}",
                             headers=headers)).status_code == 404


async def test_reactions_and_replies(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "r-owner@example.com")
    space_id, raw = await _guest_token(client, cookie, str(theme_row.id))
    headers = {"Authorization": f"Bearer {raw}"}
    posted = await client.post(f"/v1/spaces/{space_id}/contributions",
                               json={"kind": "message", "body": "React to me",
                                     "guest_name": "Zed"},
                               headers=headers)
    item_id = posted.json()["data"]["id"]

    reacted = await client.post(f"/v1/contributions/{item_id}/reactions",
                                json={"emoji": "❤"}, headers=headers)
    assert reacted.status_code == 201
    assert reacted.json()["data"]["reactions"][0]["count"] == 1
    repeat = await client.post(f"/v1/contributions/{item_id}/reactions",
                               json={"emoji": "❤"}, headers=headers)
    assert repeat.status_code == 204
    bad = await client.post(f"/v1/contributions/{item_id}/reactions",
                            json={"emoji": "not-an-emoji-allowed-here"}, headers=headers)
    assert bad.status_code == 422

    replied = await client.post(f"/v1/contributions/{item_id}/replies",
                                json={"body": "So true", "guest_name": "Amy"},
                                headers=headers)
    assert replied.status_code == 201
    replies = await client.get(f"/v1/contributions/{item_id}/replies", headers=headers)
    assert [r["body"] for r in replies.json()["data"]] == ["So true"]
    unreacted = await client.delete(f"/v1/contributions/{item_id}/reactions/❤",
                                    headers=headers)
    assert unreacted.status_code == 204


async def test_report_notifies_owner(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "rp-owner@example.com")
    space_id, raw = await _guest_token(client, cookie, str(theme_row.id))
    headers = {"Authorization": f"Bearer {raw}"}
    posted = await client.post(f"/v1/spaces/{space_id}/contributions",
                               json={"kind": "message", "body": "Questionable",
                                     "guest_name": "Zed"},
                               headers=headers)
    reported = await client.post(f"/v1/contributions/{posted.json()['data']['id']}/report",
                                 json={"reason": "Looks off"}, headers=headers)
    assert reported.status_code == 202
    mail = memory_services["mailer"].last_to("rp-owner@example.com")
    assert mail is not None and "reported" in mail.subject.lower()


async def test_feed_filters_search_and_pagination(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "l-owner@example.com")
    space_id, raw = await _guest_token(client, cookie, str(theme_row.id))
    headers = {"Authorization": f"Bearer {raw}"}
    for idx, body in enumerate(["Sunset at the beach", "Birthday cake time", "Beach games"]):
        await client.post(f"/v1/spaces/{space_id}/contributions",
                          json={"kind": "story" if idx else "message", "body": body,
                                "guest_name": "Zed"},
                          headers=headers)

    stories = await client.get(f"/v1/spaces/{space_id}/contributions?kind=story",
                               headers=headers)
    assert len(stories.json()["data"]) == 2
    search = await client.get(f"/v1/spaces/{space_id}/contributions?q=beach", headers=headers)
    assert len(search.json()["data"]) == 2
    page1 = await client.get(f"/v1/spaces/{space_id}/contributions?limit=2", headers=headers)
    assert len(page1.json()["data"]) == 2
    cursor = page1.json()["page"]["next_cursor"]
    assert cursor
    page2 = await client.get(f"/v1/spaces/{space_id}/contributions?limit=2&cursor={cursor}",
                             headers=headers)
    assert len(page2.json()["data"]) == 1
    assert page2.json()["page"]["has_more"] is False

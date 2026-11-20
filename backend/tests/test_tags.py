"""Consent-aware tagging + archived spaces (needs_pg)."""

import uuid

import pytest
from sqlalchemy import select

from app.models.spaces import SpaceMembership
from app.models.users import User
from tests.helpers import create_space, login_as

pytestmark = pytest.mark.needs_pg


async def _setup(client, memory_services):
    cookie = await login_as(client, memory_services, "tag-owner@example.com")
    member_cookie = await login_as(client, memory_services, "tag-member@example.com")
    themes = await client.get("/v1/themes", cookies={"ml_session": cookie})
    theme_id = next(t for t in themes.json()["data"] if t["plan_required"] == "free")["id"]
    data = await create_space(client, cookie, theme_id)
    space_id = data["space"]["id"]
    posted = await client.post(
        f"/v1/spaces/{space_id}/contributions",
        json={"kind": "message", "body": "Group photo day", "guest_name": "Zed"},
        cookies={"ml_session": cookie})
    return cookie, member_cookie, space_id, posted.json()["data"]["id"]


async def _user_id(session, email: str) -> str:
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    return str(user.id)


async def test_member_tag_needs_consent(client, memory_services, session):
    cookie, member_cookie, space_id, item_id = await _setup(client, memory_services)
    member_id = await _user_id(session, "tag-member@example.com")
    async with session.begin_nested():
        session.add(SpaceMembership(space_id=uuid.UUID(space_id),
                                    user_id=uuid.UUID(member_id), role="contributor"))
    await session.flush()

    suggested = await client.post(
        f"/v1/contributions/{item_id}/tags",
        json={"label": "Amy", "user_id": member_id}, cookies={"ml_session": cookie})
    assert suggested.status_code == 201
    assert suggested.json()["data"]["status"] == "pending"  # even staff can't consent for her
    tag_id = suggested.json()["data"]["id"]

    # Owner cannot approve someone else's tag.
    forbidden = await client.post(f"/v1/tags/{tag_id}/approve",
                                  cookies={"ml_session": cookie})
    assert forbidden.status_code == 403
    approved = await client.post(f"/v1/tags/{tag_id}/approve",
                                 cookies={"ml_session": member_cookie})
    assert approved.json()["data"]["status"] == "approved"


async def test_self_tag_and_staff_label_auto_approve(client, memory_services, session):
    cookie, member_cookie, space_id, item_id = await _setup(client, memory_services)
    member_id = await _user_id(session, "tag-member@example.com")
    async with session.begin_nested():
        session.add(SpaceMembership(space_id=uuid.UUID(space_id),
                                    user_id=uuid.UUID(member_id), role="contributor"))
    await session.flush()

    own = await client.post(
        f"/v1/contributions/{item_id}/tags",
        json={"label": "Me", "user_id": member_id}, cookies={"ml_session": member_cookie})
    assert own.json()["data"]["status"] == "approved"

    label = await client.post(
        f"/v1/contributions/{item_id}/tags",
        json={"label": "Uncle Joe"}, cookies={"ml_session": cookie})
    assert label.json()["data"]["status"] == "approved"

    guest_label = await client.post(
        f"/v1/contributions/{item_id}/tags",
        json={"label": "Cousin"}, cookies={"ml_session": member_cookie})
    assert guest_label.json()["data"]["status"] == "pending"


async def test_decline_and_remove(client, memory_services, session):
    cookie, member_cookie, space_id, item_id = await _setup(client, memory_services)
    member_id = await _user_id(session, "tag-member@example.com")
    async with session.begin_nested():
        session.add(SpaceMembership(space_id=uuid.UUID(space_id),
                                    user_id=uuid.UUID(member_id), role="contributor"))
    await session.flush()

    suggested = await client.post(
        f"/v1/contributions/{item_id}/tags",
        json={"label": "Amy", "user_id": member_id}, cookies={"ml_session": cookie})
    tag_id = suggested.json()["data"]["id"]
    declined = await client.post(f"/v1/tags/{tag_id}/decline",
                                 cookies={"ml_session": member_cookie})
    assert declined.json()["data"]["status"] == "declined"
    removed = await client.delete(f"/v1/tags/{tag_id}", cookies={"ml_session": cookie})
    assert removed.status_code == 204
    listed = await client.get(f"/v1/contributions/{item_id}/tags",
                              cookies={"ml_session": cookie})
    assert listed.json()["data"] == []


async def test_non_member_cannot_be_tagged(client, memory_services, session):
    cookie, _, space_id, item_id = await _setup(client, memory_services)
    outsider_cookie = await login_as(client, memory_services, "outsider@example.com")
    outsider_id = await _user_id(session, "outsider@example.com")
    denied = await client.post(
        f"/v1/contributions/{item_id}/tags",
        json={"label": "Stranger", "user_id": outsider_id},
        cookies={"ml_session": cookie})
    assert denied.status_code == 403
    _ = outsider_cookie


async def test_archived_spaces_filter(client, memory_services):
    cookie = await login_as(client, memory_services, "arch-owner@example.com")
    themes = await client.get("/v1/themes", cookies={"ml_session": cookie})
    theme_id = next(t for t in themes.json()["data"] if t["plan_required"] == "free")["id"]
    live = await create_space(client, cookie, theme_id, title="Live")
    doomed = await create_space(client, cookie, theme_id, title="Doomed")
    await client.delete(f"/v1/spaces/{doomed['space']['id']}", cookies={"ml_session": cookie})

    live_list = await client.get("/v1/spaces", cookies={"ml_session": cookie})
    titles = [entry["space"]["title"] for entry in live_list.json()["data"]]
    assert "Live" in titles and "Doomed" not in titles
    archived = await client.get("/v1/spaces?archived=true", cookies={"ml_session": cookie})
    assert [entry["space"]["title"] for entry in archived.json()["data"]] == ["Doomed"]
    _ = live

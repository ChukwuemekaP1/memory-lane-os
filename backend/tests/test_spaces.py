"""Spaces CRUD + visibility + members + tokens + invitations (needs_pg)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.scheduling import ScheduledEvent
from app.models.spaces import Theme
from tests.helpers import create_space, login_as

pytestmark = pytest.mark.needs_pg


async def test_create_space_happy_path(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "owner1@example.com")
    data = await create_space(client, cookie, str(theme_row.id), kind="family",
                              occasion="birthday", event_date="2026-06-01")
    space = data["space"]
    assert space["title"] == "Test Space"
    assert space["kind"] == "family"
    assert space["event_date"] == "2026-06-01"
    assert space["storage_quota_bytes"] > 0
    assert len(data["guest_links"]) == 2
    assert {link["token"]["role_cap"] for link in data["guest_links"]} == {"contributor", "viewer"}


async def test_create_space_validation(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "owner2@example.com")
    bad_title = await client.post("/v1/spaces",
                                  json={"title": "", "theme_id": str(theme_row.id)},
                                  cookies={"ml_session": cookie})
    assert bad_title.status_code == 422
    bad_kind = await client.post("/v1/spaces",
                                 json={"title": "T", "kind": "nope",
                                       "theme_id": str(theme_row.id)},
                                 cookies={"ml_session": cookie})
    assert bad_kind.status_code == 422
    bad_tz = await client.post("/v1/spaces",
                               json={"title": "T", "timezone": "Mars/Olympus",
                                     "theme_id": str(theme_row.id)},
                               cookies={"ml_session": cookie})
    assert bad_tz.status_code == 422
    past_publish = await client.post(
        "/v1/spaces",
        json={"title": "T", "theme_id": str(theme_row.id),
              "publish_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()},
        cookies={"ml_session": cookie})
    assert past_publish.status_code == 422


async def test_create_space_requires_auth(client, theme_row):
    response = await client.post("/v1/spaces",
                                 json={"title": "T", "theme_id": str(theme_row.id)})
    assert response.status_code == 401


async def test_create_space_premium_theme_gated(client, memory_services, session):
    cookie = await login_as(client, memory_services, "owner3@example.com")
    premium = Theme(slug="-premium-x", name="PX", occasions=["birthday"],
                    tokens={"accent": "#000"}, plan_required="premium", is_active=True)
    session.add(premium)
    await session.flush()
    response = await client.post("/v1/spaces",
                                 json={"title": "T", "theme_id": str(premium.id)},
                                 cookies={"ml_session": cookie})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "quota_exceeded"


async def test_create_space_schedules_reveal_and_reminders(client, memory_services, session,
                                                           theme_row):
    cookie = await login_as(client, memory_services, "owner4@example.com")
    publish = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    event_day = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
    data = await create_space(client, cookie, str(theme_row.id), publish_at=publish,
                              event_date=event_day, visibility="scheduled")
    assert data["space"]["publish_at"] is not None
    events = (await session.execute(
        select(ScheduledEvent).where(
            ScheduledEvent.space_id == uuid.UUID(data["space"]["id"])))
    ).scalars().all()
    kinds = sorted(event.kind.value for event in events)
    assert "reveal" in kinds and "reminder" in kinds


async def test_space_detail_visibility_matrix(client, memory_services, theme_row):
    owner_cookie = await login_as(client, memory_services, "vista-owner@example.com")
    data = await create_space(client, owner_cookie, str(theme_row.id))
    space_id = data["space"]["id"]
    contributor_link = next(link for link in data["guest_links"]
                            if link["token"]["role_cap"] == "contributor")
    raw = contributor_link["url"].split("guest=")[1]

    # Owner sees everything incl. settings + manage permission.
    detail = await client.get(f"/v1/spaces/{space_id}", cookies={"ml_session": owner_cookie})
    assert detail.status_code == 200
    body = detail.json()["data"]
    assert body["my_role"] == "owner"
    assert "manage_space" in body["my_permissions"]
    assert body["settings"] is not None

    # Guest contributor sees the space, limited permissions, no settings.
    guest = await client.get(f"/v1/spaces/{space_id}",
                             headers={"Authorization": f"Bearer {raw}"})
    assert guest.status_code == 200
    guest_body = guest.json()["data"]
    assert guest_body["my_role"] == "guest:contributor"
    assert "post" in guest_body["my_permissions"]
    assert "manage_space" not in guest_body["my_permissions"]
    assert guest_body["settings"] is None

    # Stranger on a link space: 404 (no oracle).
    stranger = await client.get(f"/v1/spaces/{space_id}")
    assert stranger.status_code == 404

    # Public space: stranger reads, but cannot post.
    await client.patch(f"/v1/spaces/{space_id}", json={"visibility": "public"},
                       cookies={"ml_session": owner_cookie})
    pub = await client.get(f"/v1/spaces/{space_id}")
    assert pub.status_code == 200
    assert "post" not in pub.json()["data"]["my_permissions"]

    # Private space: guest token grants nothing.
    await client.patch(f"/v1/spaces/{space_id}", json={"visibility": "private"},
                       cookies={"ml_session": owner_cookie})
    locked = await client.get(f"/v1/spaces/{space_id}",
                              headers={"Authorization": f"Bearer {raw}"})
    assert locked.status_code == 404


async def test_delete_restore_purge_flow(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "del-owner@example.com")
    data = await create_space(client, cookie, str(theme_row.id), title="Delete Me")
    space_id = data["space"]["id"]

    gone = await client.delete(f"/v1/spaces/{space_id}", cookies={"ml_session": cookie})
    assert gone.status_code == 204
    # Owner still reads (for restore); strangers 404.
    assert (await client.get(f"/v1/spaces/{space_id}",
                             cookies={"ml_session": cookie})).status_code == 200
    assert (await client.get(f"/v1/spaces/{space_id}")).status_code == 404

    restored = await client.post(f"/v1/spaces/{space_id}/restore",
                                 cookies={"ml_session": cookie})
    assert restored.status_code == 200
    assert restored.json()["data"]["space"]["deleted_at"] is None

    wrong_confirm = await client.post(f"/v1/spaces/{space_id}/purge",
                                      json={"confirm_title": "Wrong"},
                                      cookies={"ml_session": cookie})
    assert wrong_confirm.status_code == 422
    purged = await client.post(f"/v1/spaces/{space_id}/purge",
                               json={"confirm_title": "Delete Me"},
                               cookies={"ml_session": cookie})
    assert purged.status_code == 202
    assert "purge_archive_id" in purged.json()["data"]


async def test_transfer_ownership(client, memory_services, session, theme_row):
    from app.models.users import User

    owner_cookie = await login_as(client, memory_services, "t-owner@example.com")
    await login_as(client, memory_services, "t-new@example.com")
    data = await create_space(client, owner_cookie, str(theme_row.id))
    space_id = data["space"]["id"]
    new_owner = (await session.execute(
        select(User).where(User.email == "t-new@example.com"))).scalar_one()

    transfer = await client.post(f"/v1/spaces/{space_id}/transfer",
                                 json={"new_owner_user_id": str(new_owner.id)},
                                 cookies={"ml_session": owner_cookie})
    assert transfer.status_code == 200
    assert transfer.json()["data"]["my_role"] == "collaborator"


async def test_guest_token_mint_revoke_cycle(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "tok-owner@example.com")
    data = await create_space(client, cookie, str(theme_row.id))
    space_id = data["space"]["id"]

    minted = await client.post(f"/v1/spaces/{space_id}/guest-tokens",
                               json={"label": "Party QR", "role_cap": "contributor",
                                     "max_uses": 10},
                               cookies={"ml_session": cookie})
    assert minted.status_code == 201
    minted_body = minted.json()["data"]
    assert minted_body["url"].startswith("http")
    assert len(minted_body["token_preview"]) == 8
    token_id = minted_body["token"]["id"]

    listed = await client.get(f"/v1/spaces/{space_id}/guest-tokens",
                              cookies={"ml_session": cookie})
    assert len(listed.json()["data"]) == 3  # 2 defaults + 1 minted

    revoked = await client.post(f"/v1/guest-tokens/{token_id}/revoke",
                                cookies={"ml_session": cookie})
    assert revoked.status_code == 200
    raw = minted_body["url"].split("guest=")[1]
    dead = await client.get(f"/v1/spaces/{space_id}",
                            headers={"Authorization": f"Bearer {raw}"})
    assert dead.status_code == 404  # lenient read path: invalid token, no actor


async def test_invitation_lifecycle(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "inv-owner@example.com")
    data = await create_space(client, cookie, str(theme_row.id))
    space_id = data["space"]["id"]

    invited = await client.post(f"/v1/spaces/{space_id}/invitations",
                                json={"email": "friend@example.com", "role": "contributor"},
                                cookies={"ml_session": cookie})
    assert invited.status_code == 202
    mail = memory_services["mailer"].last_to("friend@example.com")
    assert mail is not None and "/invite/" in mail.text_body
    raw = mail.text_body.split("/invite/")[1].split()[0].strip()

    preview = await client.get(f"/v1/invitations/{raw}")
    assert preview.json()["data"]["role"] == "contributor"

    friend_cookie = await login_as(client, memory_services, "friend@example.com")
    accepted = await client.post(f"/v1/invitations/{raw}/accept",
                                 cookies={"ml_session": friend_cookie})
    assert accepted.status_code == 200
    assert accepted.json()["data"]["role"] == "contributor"

    members = await client.get(f"/v1/spaces/{space_id}/members",
                               cookies={"ml_session": cookie})
    assert any(m["email"] == "friend@example.com" for m in members.json()["data"])

    again = await client.post(f"/v1/invitations/{raw}/accept",
                              cookies={"ml_session": friend_cookie})
    assert again.status_code == 409


async def test_member_role_change_and_leave(client, memory_services, session, theme_row):
    from app.models.spaces import SpaceMembership
    from app.models.users import User

    cookie = await login_as(client, memory_services, "mem-owner@example.com")
    member_cookie = await login_as(client, memory_services, "mem-member@example.com")
    data = await create_space(client, cookie, str(theme_row.id))
    space_id = data["space"]["id"]
    member = (await session.execute(
        select(User).where(User.email == "mem-member@example.com"))).scalar_one()
    session.add(SpaceMembership(space_id=uuid.UUID(space_id), user_id=member.id,
                                role="viewer"))
    await session.flush()

    promoted = await client.patch(f"/v1/spaces/{space_id}/members/{member.id}",
                                  json={"role": "collaborator"},
                                  cookies={"ml_session": cookie})
    assert promoted.json()["data"]["role"] == "collaborator"

    left = await client.delete(f"/v1/spaces/{space_id}/members/{member.id}",
                               cookies={"ml_session": member_cookie})
    assert left.status_code == 204


async def test_purge_executes_and_removes_everything(committed_client, memory_services):
    from app import db
    from app.models.spaces import Space
    from app.services.storage import get_storage

    cookie = await login_as(committed_client, memory_services, "purge-owner@example.com")
    themes = await committed_client.get("/v1/themes", cookies={"ml_session": cookie})
    theme_id = next(t for t in themes.json()["data"] if t["plan_required"] == "free")["id"]
    data = await create_space(committed_client, cookie, theme_id, title="Purge Me")
    space_id = data["space"]["id"]
    raw = next(link for link in data["guest_links"]
               if link["token"]["role_cap"] == "contributor")["url"].split("guest=")[1]
    await committed_client.post(
        f"/v1/spaces/{space_id}/contributions",
        json={"kind": "message", "body": "bye", "guest_name": "Zed"},
        headers={"Authorization": f"Bearer {raw}"})

    purged = await committed_client.post(
        f"/v1/spaces/{space_id}/purge", json={"confirm_title": "Purge Me"},
        cookies={"ml_session": cookie})
    assert purged.status_code == 202
    async with db.session_scope() as session:
        assert await session.get(Space, uuid.UUID(space_id)) is None
    storage = get_storage()
    assert await storage.delete_prefix(f"originals/{space_id}") == 0  # already gone


async def test_collaborator_field_subset(client, memory_services, session, theme_row):
    from app.models.spaces import SpaceMembership
    from app.models.users import User

    cookie = await login_as(client, memory_services, "sub-owner@example.com")
    collab_cookie = await login_as(client, memory_services, "sub-collab@example.com")
    data = await create_space(client, cookie, str(theme_row.id))
    space_id = data["space"]["id"]
    collab = (await session.execute(
        select(User).where(User.email == "sub-collab@example.com"))).scalar_one()
    session.add(SpaceMembership(space_id=uuid.UUID(space_id), user_id=collab.id,
                                role="collaborator"))
    await session.flush()

    ok = await client.patch(f"/v1/spaces/{space_id}", json={"title": "New Title"},
                            cookies={"ml_session": collab_cookie})
    assert ok.status_code == 200
    denied = await client.patch(f"/v1/spaces/{space_id}", json={"visibility": "public"},
                                cookies={"ml_session": collab_cookie})
    assert denied.status_code == 403

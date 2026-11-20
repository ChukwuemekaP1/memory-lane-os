"""Theme catalog, preview, customization, and content-safety (needs_pg)."""

import pytest
from sqlalchemy import select

from app.models.spaces import Space, Theme
from tests.helpers import create_space, login_as

pytestmark = pytest.mark.needs_pg


async def test_theme_catalog_filter_and_entitled(client, memory_services, session):
    cookie = await login_as(client, memory_services, "theme-user@example.com")
    session.add(Theme(slug="wed-x", name="Wed X", occasions=["wedding"],
                      tokens={"accent": "#fff"}, plan_required="free", is_active=True))
    session.add(Theme(slug="prem-x", name="Prem X", occasions=["birthday"],
                      tokens={"accent": "#000"}, plan_required="premium", is_active=True))
    await session.flush()

    catalog = await client.get("/v1/themes", cookies={"ml_session": cookie})
    assert catalog.status_code == 200
    assert any(t["slug"] == "wed-x" for t in catalog.json()["data"])

    filtered = await client.get("/v1/themes?occasion=wedding",
                                cookies={"ml_session": cookie})
    slugs = [t["slug"] for t in filtered.json()["data"]]
    assert "wed-x" in slugs and "prem-x" not in slugs

    premium = next(t for t in catalog.json()["data"] if t["slug"] == "prem-x")
    assert premium["entitled"] is False  # free plan


async def test_theme_preview_merges_without_saving(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "prev-owner@example.com")
    data = await create_space(client, cookie, str(theme_row.id))
    space_id = data["space"]["id"]

    preview = await client.post(
        f"/v1/spaces/{space_id}/theme-preview",
        json={"overrides": {"accent": "#123456", "font": "serif"}},
        cookies={"ml_session": cookie})
    assert preview.status_code == 200
    body = preview.json()["data"]
    assert body["tokens"]["accent"] == "#123456"
    assert body["tokens"]["font"] == "serif"
    assert body["is_customized"] is True

    detail = await client.get(f"/v1/spaces/{space_id}", cookies={"ml_session": cookie})
    assert detail.json()["data"]["theme"]["is_customized"] is False  # unchanged


async def test_theme_preview_rejects_unknown_keys(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "prev2-owner@example.com")
    data = await create_space(client, cookie, str(theme_row.id))
    bad = await client.post(f"/v1/spaces/{data['space']['id']}/theme-preview",
                            json={"overrides": {"evil": "x"}},
                            cookies={"ml_session": cookie})
    assert bad.status_code == 422


async def test_customize_theme_overrides(client, memory_services, theme_row):
    cookie = await login_as(client, memory_services, "cust-owner@example.com")
    data = await create_space(client, cookie, str(theme_row.id))
    space_id = data["space"]["id"]

    patched = await client.patch(
        f"/v1/spaces/{space_id}", json={"theme_overrides": {"background": "#abcdef"}},
        cookies={"ml_session": cookie})
    assert patched.status_code == 200
    theme = patched.json()["data"]["theme"]
    assert theme["is_customized"] is True
    assert theme["tokens"]["background"] == "#abcdef"
    assert theme["tokens"]["accent"] == "#000"  # base token preserved


async def test_changing_theme_preserves_content_and_permissions(
    client, memory_services, session, theme_row
):
    cookie = await login_as(client, memory_services, "safe-owner@example.com")
    data = await create_space(client, cookie, str(theme_row.id))
    space_id = data["space"]["id"]
    raw = next(link for link in data["guest_links"]
               if link["token"]["role_cap"] == "contributor")["url"].split("guest=")[1]

    # Guest posts before the theme change.
    posted = await client.post(
        f"/v1/spaces/{space_id}/contributions",
        json={"kind": "message", "body": "Happy day!", "guest_name": "Zed"},
        headers={"Authorization": f"Bearer {raw}"})
    assert posted.status_code == 201
    before_perms = (await client.get(
        f"/v1/spaces/{space_id}", headers={"Authorization": f"Bearer {raw}"})
    ).json()["data"]["my_permissions"]

    other = Theme(slug="other-x", name="Other", occasions=["birthday"],
                  tokens={"accent": "#111"}, plan_required="free", is_active=True)
    session.add(other)
    await session.flush()
    changed = await client.patch(f"/v1/spaces/{space_id}",
                                 json={"theme_id": str(other.id),
                                       "theme_overrides": {"font": "mono"}},
                                 cookies={"ml_session": cookie})
    assert changed.status_code == 200

    # Content identical, permissions identical, only tokens differ.
    visible = await client.get(
        f"/v1/spaces/{space_id}/contributions",
        headers={"Authorization": f"Bearer {raw}"})
    assert visible.status_code == 200
    assert [c["body"] for c in visible.json()["data"]] == ["Happy day!"]
    after_perms = (await client.get(
        f"/v1/spaces/{space_id}", headers={"Authorization": f"Bearer {raw}"})
    ).json()["data"]["my_permissions"]
    assert after_perms == before_perms
    detail = await client.get(f"/v1/spaces/{space_id}", cookies={"ml_session": cookie})
    assert detail.json()["data"]["theme"]["tokens"]["font"] == "mono"

    # And the DB row itself is untouched apart from theme columns.
    space = await session.get(Space, space_id)
    assert space.title == "Test Space"
    assert space.contribution_policy.value == "link_contributors"

"""Archive exports + preservation workflows (needs_pg)."""

import io
import shutil
import uuid
import zipfile

import pytest
from sqlalchemy import select

from app.models.archives import Archive, Subscription
from app.models.users import User
from tests.helpers import create_space, login_as
from tests.test_media import png_bytes

pytestmark = pytest.mark.needs_pg

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                  reason="ffmpeg is not installed")


async def _space(committed_client, memory_services, email="ex-owner@example.com", **overrides):
    cookie = await login_as(committed_client, memory_services, email)
    themes = await committed_client.get("/v1/themes", cookies={"ml_session": cookie})
    theme_id = next(t for t in themes.json()["data"] if t["plan_required"] == "free")["id"]
    data = await create_space(committed_client, cookie, theme_id, **overrides)
    return cookie, data["space"]["id"]


async def _upload_bytes(committed_client, cookie, space_id, data, mime, kind):
    from app import db
    from app.models.contributions import MediaAsset
    from app.services.storage import get_storage

    presigned = await committed_client.post(
        "/v1/media/presign",
        json={"space_id": space_id, "mime": mime, "bytes": len(data), "kind": kind},
        cookies={"ml_session": cookie})
    asset_id = presigned.json()["data"]["id"]
    async with db.session_scope() as session:
        asset = await session.get(MediaAsset, uuid.UUID(asset_id))
        key = asset.original_key
    await get_storage().write_bytes(key, data, mime)
    await committed_client.post("/v1/media/confirm", json={"asset_id": asset_id},
                                cookies={"ml_session": cookie})
    return asset_id


async def test_full_zip_roundtrip(committed_client, memory_services):
    cookie, space_id = await _space(committed_client, memory_services)
    await committed_client.post(
        f"/v1/spaces/{space_id}/contributions",
        json={"kind": "message", "body": "Keep me", "guest_name": "Zed"},
        cookies={"ml_session": cookie})
    raw = png_bytes() if shutil.which("ffmpeg") else b"fake-image-bytes"
    await _upload_bytes(committed_client, cookie, space_id, raw, "image/png", "image")

    requested = await committed_client.post(f"/v1/spaces/{space_id}/archives",
                                            json={"kind": "full_zip"},
                                            cookies={"ml_session": cookie})
    assert requested.status_code == 202
    listed = await committed_client.get(f"/v1/spaces/{space_id}/archives",
                                        cookies={"ml_session": cookie})
    entry = next(a for a in listed.json()["data"]
                 if a["id"] == requested.json()["data"]["archive_id"])
    assert entry["status"] == "succeeded"
    assert entry["download_url"].endswith("/download")

    from app import db
    from app.services.storage import get_storage

    async with db.session_scope() as session:
        archive = await session.get(Archive, uuid.UUID(entry["id"]))
        key = f"exports/{space_id}/{archive.id}.zip"
    blob = await get_storage().read_bytes(key)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive_file:
        names = sorted(archive_file.namelist())
        assert "data.json" in names and "manifest.json" in names
        assert any(name.startswith("originals/") for name in names)
        assert b"Keep me" in archive_file.read("data.json")


async def test_collaborator_export_excludes_private(committed_client, memory_services, session):
    from app import db
    from app.models.spaces import SpaceMembership
    from app.models.users import User as UserModel
    from app.services.storage import get_storage

    cookie, space_id = await _space(committed_client, memory_services,
                                    email="co-owner@example.com")
    collab_cookie = await login_as(committed_client, memory_services, "co-collab@example.com")
    async with db.session_scope() as owned:
        collab = (await owned.execute(select(UserModel).where(
            UserModel.email == "co-collab@example.com"))).scalar_one()
        owned.add(SpaceMembership(space_id=uuid.UUID(space_id), user_id=collab.id,
                                  role="collaborator"))
    await committed_client.post(
        f"/v1/spaces/{space_id}/contributions",
        json={"kind": "private_note", "body": "Owner eyes only", "guest_name": "Zed"},
        cookies={"ml_session": cookie})
    requested = await committed_client.post(
        f"/v1/spaces/{space_id}/archives", json={"kind": "data_export"},
        cookies={"ml_session": collab_cookie})
    archive_id = requested.json()["data"]["archive_id"]
    async with db.session_scope() as owned:
        archive = await owned.get(Archive, uuid.UUID(archive_id))
        assert archive.status.value == "succeeded"
    blob = await get_storage().read_bytes(f"exports/{space_id}/{archive_id}.zip")
    with zipfile.ZipFile(io.BytesIO(blob)) as archive_file:
        assert b"Owner eyes only" not in archive_file.read("data.json")


async def test_book_pdf_premium_gate_and_build(committed_client, memory_services):
    from app import db

    cookie, space_id = await _space(committed_client, memory_services,
                                    email="book-owner@example.com")
    await committed_client.post(
        f"/v1/spaces/{space_id}/contributions",
        json={"kind": "story", "body": "Once upon a time", "guest_name": "Zed"},
        cookies={"ml_session": cookie})
    gated = await committed_client.post(f"/v1/spaces/{space_id}/archives",
                                        json={"kind": "book_pdf"},
                                        cookies={"ml_session": cookie})
    assert gated.status_code == 403
    async with db.session_scope() as session:
        owner = (await session.execute(select(User).where(
            User.email == "book-owner@example.com"))).scalar_one()
        session.add(Subscription(user_id=owner.id, plan="premium", provider="none",
                                 status="active", cancel_at_period_end=False))
    requested = await committed_client.post(f"/v1/spaces/{space_id}/archives",
                                            json={"kind": "book_pdf"},
                                            cookies={"ml_session": cookie})
    archive_id = requested.json()["data"]["archive_id"]
    from app.services.storage import get_storage

    blob = await get_storage().read_bytes(f"exports/{space_id}/{archive_id}.pdf")
    assert blob.startswith(b"%PDF-1.4")
    assert b"Once upon a time" in blob


@needs_ffmpeg
async def test_film_export_needs_photos(committed_client, memory_services):
    cookie, space_id = await _space(committed_client, memory_services,
                                    email="film-owner@example.com")
    from app import db

    async with db.session_scope() as session:
        owner = (await session.execute(select(User).where(
            User.email == "film-owner@example.com"))).scalar_one()
        session.add(Subscription(user_id=owner.id, plan="premium", provider="none",
                                 status="active", cancel_at_period_end=False))
    empty = await committed_client.post(f"/v1/spaces/{space_id}/archives",
                                        json={"kind": "film_mp4"},
                                        cookies={"ml_session": cookie})
    listed = await committed_client.get(f"/v1/spaces/{space_id}/archives",
                                        cookies={"ml_session": cookie})
    failed = next(a for a in listed.json()["data"]
                  if a["id"] == empty.json()["data"]["archive_id"])
    assert failed["status"] == "dead"
    assert "photo" in (failed["last_error"] or "").lower()


async def test_download_auth_expiry_and_share_link(committed_client, memory_services):
    from datetime import datetime, timedelta, timezone

    from app import db

    cookie, space_id = await _space(committed_client, memory_services,
                                    email="dl2-owner@example.com")
    requested = await committed_client.post(f"/v1/spaces/{space_id}/archives",
                                            json={"kind": "data_export"},
                                            cookies={"ml_session": cookie})
    archive_id = requested.json()["data"]["archive_id"]

    stranger = await committed_client.get(f"/v1/archives/{archive_id}/download",
                                          follow_redirects=False)
    assert stranger.status_code == 404
    owner = await committed_client.get(f"/v1/archives/{archive_id}/download",
                                       cookies={"ml_session": cookie},
                                       follow_redirects=False)
    assert owner.status_code == 302

    shared = await committed_client.post(f"/v1/archives/{archive_id}/share-link",
                                         cookies={"ml_session": cookie})
    token = shared.json()["data"]["url"].split("?t=")[1]
    via_token = await committed_client.get(f"/v1/archives/{archive_id}/download?t={token}",
                                           follow_redirects=False)
    assert via_token.status_code == 302
    wrong = await committed_client.get(f"/v1/archives/{archive_id}/download?t={'ab' * 32}",
                                       follow_redirects=False)
    assert wrong.status_code == 404

    async with db.session_scope() as session:
        archive = await session.get(Archive, uuid.UUID(archive_id))
        archive.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    expired = await committed_client.get(f"/v1/archives/{archive_id}/download?t={token}",
                                         cookies={"ml_session": cookie},
                                         follow_redirects=False)
    assert expired.status_code == 410


async def test_personal_export(committed_client, memory_services):
    cookie, _ = await _space(committed_client, memory_services,
                             email="personal-owner@example.com")
    requested = await committed_client.get("/v1/me/export", cookies={"ml_session": cookie})
    assert requested.status_code == 202
    listed = await committed_client.get("/v1/me/archives", cookies={"ml_session": cookie})
    assert len(listed.json()["data"]) == 1
    assert listed.json()["data"][0]["status"] == "succeeded"


async def test_close_account_flow(committed_client, memory_services):
    from app import db

    cookie = await login_as(committed_client, memory_services, "bye-owner@example.com")
    themes = await committed_client.get("/v1/themes", cookies={"ml_session": cookie})
    theme_id = next(t for t in themes.json()["data"] if t["plan_required"] == "free")["id"]
    data = await create_space(committed_client, cookie, theme_id, title="Mine")
    space_id = data["space"]["id"]

    blocked = await committed_client.post("/v1/me/delete",
                                          json={"confirm_email": "bye-owner@example.com"},
                                          cookies={"ml_session": cookie})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["details"]["spaces"][0]["title"] == "Mine"

    await login_as(committed_client, memory_services, "heir@example.com")
    async with db.session_scope() as session:
        heir = (await session.execute(select(User).where(
            User.email == "heir@example.com"))).scalar_one()
        heir_id = str(heir.id)
    transferred = await committed_client.post(
        f"/v1/spaces/{space_id}/transfer", json={"new_owner_user_id": heir_id},
        cookies={"ml_session": cookie})
    assert transferred.status_code == 200
    closed = await committed_client.post("/v1/me/delete",
                                         json={"confirm_email": "bye-owner@example.com"},
                                         cookies={"ml_session": cookie})
    assert closed.status_code == 202
    assert (await committed_client.get("/v1/auth/me",
                                       cookies={"ml_session": cookie})).json()["data"]["actor"] is None


async def test_purge_account_scrubs_everything(committed_client, memory_services):
    from app import db
    from app.models.contributions import Contribution
    from app.models.users import UserSession

    cookie = await login_as(committed_client, memory_services, "scrub-owner@example.com")
    themes = await committed_client.get("/v1/themes", cookies={"ml_session": cookie})
    theme_id = next(t for t in themes.json()["data"] if t["plan_required"] == "free")["id"]
    data = await create_space(committed_client, cookie, theme_id, title="Temp")
    space_id = data["space"]["id"]
    posted = await committed_client.post(
        f"/v1/spaces/{space_id}/contributions",
        json={"kind": "message", "body": "My words", "guest_name": "Zed"},
        cookies={"ml_session": cookie})
    item_id = posted.json()["data"]["id"]

    # Live owned spaces block purging too.
    blocked = await committed_client.post("/v1/me/purge",
                                          json={"confirm_email": "scrub-owner@example.com"},
                                          cookies={"ml_session": cookie})
    assert blocked.status_code == 409
    await committed_client.delete(f"/v1/spaces/{space_id}", cookies={"ml_session": cookie})

    purged = await committed_client.post("/v1/me/purge",
                                         json={"confirm_email": "scrub-owner@example.com"},
                                         cookies={"ml_session": cookie})
    assert purged.status_code == 202

    async with db.session_scope() as session:
        user = (await session.execute(select(User).where(
            User.email.like("deleted-%@deleted.local")))).scalars().all()
        mine = [u for u in user if u.display_name == "Deleted member"]
        assert len(mine) == 1
        assert mine[0].deleted_at is not None
        item = await session.get(Contribution, uuid.UUID(item_id))
        assert item.author_user_id is None
        assert item.author_snapshot == "Deleted member"
        sessions = (await session.execute(select(UserSession).where(
            UserSession.user_id == mine[0].id))).scalars().all()
        assert sessions == []

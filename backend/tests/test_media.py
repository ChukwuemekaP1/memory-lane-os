"""Signed-upload + processing journeys (needs_pg; processing needs ffmpeg)."""

import math
import shutil
import struct
import subprocess
import uuid
import wave

import pytest

from app.models.contributions import MediaAsset
from app.models.spaces import Space
from app.services.storage import get_storage
from tests.helpers import create_space, login_as

pytestmark = pytest.mark.needs_pg

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                  reason="ffmpeg is not installed")


def _ffmpeg(*args: str) -> bytes:
    completed = subprocess.run([shutil.which("ffmpeg"), "-y", "-v", "error", *args],
                               capture_output=True, timeout=120)
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")[-500:]
    return completed.stdout


def png_bytes(size: int = 64) -> bytes:
    import tempfile, os
    path = os.path.join(tempfile.gettempdir(), f"ml-test-{uuid.uuid4().hex}.png")
    _ffmpeg("-f", "lavfi", "-i", f"testsrc=size={size}x{size}:rate=1:duration=0.1",
            "-frames:v", "1", path)
    with open(path, "rb") as handle:
        return handle.read()


def mp4_bytes() -> bytes:
    import tempfile, os
    path = os.path.join(tempfile.gettempdir(), f"ml-test-{uuid.uuid4().hex}.mp4")
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=1",
            "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", path)
    with open(path, "rb") as handle:
        return handle.read()


def wav_bytes(seconds: float = 1.0) -> bytes:
    import io
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        frames = int(8000 * seconds)
        wav.writeframes(b"".join(
            struct.pack("<h", int(10000 * math.sin(i * 0.1))) for i in range(frames)))
    return buffer.getvalue()


async def _upload(client, cookie, space_id, data, mime, kind):
    """Full client flow: presign → PUT bytes → confirm. Returns confirm body."""
    presigned = await client.post("/v1/media/presign",
                                  json={"space_id": space_id, "mime": mime,
                                        "bytes": len(data), "kind": kind},
                                  cookies={"ml_session": cookie})
    assert presigned.status_code == 201, presigned.text
    body = presigned.json()["data"]
    storage = get_storage()
    await storage.write_bytes(await _key_for(body["id"]), data, mime)
    confirmed = await client.post("/v1/media/confirm", json={"asset_id": body["id"]},
                                  cookies={"ml_session": cookie})
    assert confirmed.status_code == 202, confirmed.text
    return confirmed.json()["data"]


async def _key_for(asset_id: str) -> str:
    from app import db

    async with db.session_scope() as session:
        asset = await session.get(MediaAsset, uuid.UUID(asset_id))
        assert asset is not None
        return asset.original_key


async def test_presign_happy_path(committed_client, memory_services):
    cookie = await login_as(committed_client, memory_services, "up-owner@example.com")
    theme = await _theme_id(committed_client, cookie)
    data = await create_space(committed_client, cookie, theme)
    response = await committed_client.post(
        "/v1/media/presign",
        json={"space_id": data["space"]["id"], "mime": "image/jpeg", "bytes": 1000},
        cookies={"ml_session": cookie})
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["status"] == "reserved"
    assert body["upload_url"]
    assert body["kind"] == "image"


async def test_presign_validation(committed_client, memory_services):
    cookie = await login_as(committed_client, memory_services, "up2-owner@example.com")
    theme = await _theme_id(committed_client, cookie)
    data = await create_space(committed_client, cookie, theme)
    space_id = data["space"]["id"]

    bad_mime = await committed_client.post(
        "/v1/media/presign",
        json={"space_id": space_id, "mime": "application/x-evil", "bytes": 10},
        cookies={"ml_session": cookie})
    assert bad_mime.status_code == 415
    too_big = await committed_client.post(
        "/v1/media/presign",
        json={"space_id": space_id, "mime": "image/jpeg", "bytes": 30 * 1024 * 1024},
        cookies={"ml_session": cookie})
    assert too_big.status_code == 413
    mismatch = await committed_client.post(
        "/v1/media/presign",
        json={"space_id": space_id, "mime": "image/jpeg", "bytes": 10, "kind": "video"},
        cookies={"ml_session": cookie})
    assert mismatch.status_code == 422


async def test_presign_quota_and_auth(committed_client, memory_services):
    from app import db

    cookie = await login_as(committed_client, memory_services, "up3-owner@example.com")
    theme = await _theme_id(committed_client, cookie)
    data = await create_space(committed_client, cookie, theme)
    space_id = data["space"]["id"]
    async with db.session_scope() as session:
        space = await session.get(Space, uuid.UUID(space_id))
        space.storage_quota_bytes = 100
    full = await committed_client.post(
        "/v1/media/presign",
        json={"space_id": space_id, "mime": "image/jpeg", "bytes": 101},
        cookies={"ml_session": cookie})
    assert full.status_code == 403
    assert full.json()["error"]["code"] == "quota_exceeded"
    stranger = await committed_client.post(
        "/v1/media/presign",
        json={"space_id": space_id, "mime": "image/jpeg", "bytes": 10})
    assert stranger.status_code in (401, 404)


async def test_confirm_requires_bytes_then_size(committed_client, memory_services):
    cookie = await login_as(committed_client, memory_services, "cf-owner@example.com")
    theme = await _theme_id(committed_client, cookie)
    data = await create_space(committed_client, cookie, theme)
    presigned = await committed_client.post(
        "/v1/media/presign",
        json={"space_id": data["space"]["id"], "mime": "image/jpeg", "bytes": 100},
        cookies={"ml_session": cookie})
    asset_id = presigned.json()["data"]["id"]
    early = await committed_client.post("/v1/media/confirm", json={"asset_id": asset_id},
                                        cookies={"ml_session": cookie})
    assert early.status_code == 409
    storage = get_storage()
    await storage.write_bytes(await _key_for(asset_id), b"x" * 50, "image/jpeg")
    mismatch = await committed_client.post("/v1/media/confirm", json={"asset_id": asset_id},
                                           cookies={"ml_session": cookie})
    assert mismatch.status_code == 409


@needs_ffmpeg
async def test_image_full_journey(committed_client, memory_services):
    cookie = await login_as(committed_client, memory_services, "img-owner@example.com")
    theme = await _theme_id(committed_client, cookie)
    data = await create_space(committed_client, cookie, theme)
    space_id = data["space"]["id"]
    raw = png_bytes()

    confirmed = await _upload(committed_client, cookie, space_id, raw, "image/png", "image")
    assert confirmed["job_status"] in ("queued", "running", "succeeded")
    asset_id = confirmed["asset"]["id"]

    job = await committed_client.get(f"/v1/media/jobs/{confirmed['processing_job_id']}",
                                     cookies={"ml_session": cookie})
    assert job.json()["data"]["status"] == "succeeded"

    asset = await committed_client.get(f"/v1/media/{asset_id}",
                                       cookies={"ml_session": cookie})
    body = asset.json()["data"]
    assert body["status"] == "ready"
    assert body["width"] == 64 and body["height"] == 64
    labels = {name for name in body["urls"]["derivatives"]}
    assert labels == {"thumb", "preview"}
    assert "original" in body["urls"]  # owner sees originals

    storage = get_storage()
    assert await storage.read_bytes(await _key_for(asset_id)) == raw  # original preserved


@needs_ffmpeg
async def test_failed_processing_then_retry(committed_client, memory_services):
    cookie = await login_as(committed_client, memory_services, "fail-owner@example.com")
    theme = await _theme_id(committed_client, cookie)
    data = await create_space(committed_client, cookie, theme)
    space_id = data["space"]["id"]
    good = png_bytes()
    n = len(good)

    presigned = await committed_client.post(
        "/v1/media/presign",
        json={"space_id": space_id, "mime": "image/png", "bytes": n, "kind": "image"},
        cookies={"ml_session": cookie})
    asset_id = presigned.json()["data"]["id"]
    storage = get_storage()
    key = await _key_for(asset_id)
    await storage.write_bytes(key, b"garbage-bytes!!"[:n].ljust(n, b"0"), "image/png")
    confirmed = await committed_client.post("/v1/media/confirm", json={"asset_id": asset_id},
                                            cookies={"ml_session": cookie})
    job_id = confirmed.json()["data"]["processing_job_id"]
    # Deferred-eager runs post-commit: single attempt, recorded failure.
    job = await committed_client.get(f"/v1/media/jobs/{job_id}",
                                     cookies={"ml_session": cookie})
    assert job.json()["data"]["status"] == "failed"
    assert job.json()["data"]["last_error"]

    await storage.write_bytes(key, good, "image/png")
    retry = await committed_client.post("/v1/media/confirm", json={"asset_id": asset_id},
                                        cookies={"ml_session": cookie})
    assert retry.status_code == 202
    assert retry.json()["data"]["processing_job_id"] != job_id
    done = await committed_client.get(f"/v1/media/jobs/{retry.json()['data']['processing_job_id']}",
                                      cookies={"ml_session": cookie})
    assert done.json()["data"]["status"] == "succeeded"


@needs_ffmpeg
async def test_video_and_audio_derivatives(committed_client, memory_services):
    cookie = await login_as(committed_client, memory_services, "va-owner@example.com")
    theme = await _theme_id(committed_client, cookie)
    data = await create_space(committed_client, cookie, theme)
    space_id = data["space"]["id"]

    video = await _upload(committed_client, cookie, space_id, mp4_bytes(), "video/mp4", "video")
    vasset = await committed_client.get(f"/v1/media/{video['asset']['id']}",
                                        cookies={"ml_session": cookie})
    vbody = vasset.json()["data"]
    assert vbody["status"] == "ready"
    assert set(vbody["urls"]["derivatives"]) == {"preview", "poster"}
    assert (vbody["duration_ms"] or 0) > 0

    audio = await _upload(committed_client, cookie, space_id, wav_bytes(), "audio/wav", "audio")
    aasset = await committed_client.get(f"/v1/media/{audio['asset']['id']}",
                                        cookies={"ml_session": cookie})
    abody = aasset.json()["data"]
    assert abody["status"] == "ready"
    assert set(abody["urls"]["derivatives"]) == {"preview"}
    assert (abody["duration_ms"] or 0) > 0


async def test_download_policy_and_delete(committed_client, memory_services):
    from app import db

    cookie = await login_as(committed_client, memory_services, "dl-owner@example.com")
    theme = await _theme_id(committed_client, cookie)
    data = await create_space(committed_client, cookie, theme)
    space_id = data["space"]["id"]
    viewer_raw = next(link for link in data["guest_links"]
                      if link["token"]["role_cap"] == "viewer")["url"].split("guest=")[1]
    presigned = await committed_client.post(
        "/v1/media/presign",
        json={"space_id": space_id, "mime": "image/jpeg", "bytes": 10},
        cookies={"ml_session": cookie})
    asset_id = presigned.json()["data"]["id"]

    viewer_headers = {"Authorization": f"Bearer {viewer_raw}"}
    original_for_viewer = await committed_client.get(
        f"/v1/media/{asset_id}/download", headers=viewer_headers, follow_redirects=False)
    assert original_for_viewer.status_code == 403
    unknown_derivative = await committed_client.get(
        f"/v1/media/{asset_id}/download?derivative=nope",
        cookies={"ml_session": cookie}, follow_redirects=False)
    assert unknown_derivative.status_code == 404

    async with db.session_scope() as session:
        before = (await session.get(Space, uuid.UUID(space_id))).storage_used_bytes
    deleted = await committed_client.delete(f"/v1/media/{asset_id}",
                                            cookies={"ml_session": cookie})
    assert deleted.status_code == 204
    async with db.session_scope() as session:
        after = (await session.get(Space, uuid.UUID(space_id))).storage_used_bytes
    assert after <= before
    storage = get_storage()
    assert not await storage.exists(await _key_for(asset_id))


async def _theme_id(client, cookie: str) -> str:
    themes = await client.get("/v1/themes", cookies={"ml_session": cookie})
    assert themes.status_code == 200, themes.text
    free = [t for t in themes.json()["data"] if t["plan_required"] == "free"]
    assert free, "seeded free theme missing (migrations not applied?)"
    return free[0]["id"]

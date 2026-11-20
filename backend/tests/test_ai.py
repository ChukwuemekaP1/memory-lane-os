"""AI Studio journeys (needs_pg; fake provider; media paths need ffmpeg)."""

import shutil
import uuid

import pytest
from sqlalchemy import select

from app.models.ai import AIGenerationJob
from app.models.contributions import Contribution, MediaAsset
from app.services.ai.providers import AIError, AIResult, reset_ai_provider, set_ai_provider
from tests.helpers import create_space, login_as
from tests.test_media import mp4_bytes, png_bytes, wav_bytes

pytestmark = pytest.mark.needs_pg

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                  reason="ffmpeg is not installed")


@pytest.fixture
async def studio_space(committed_client, memory_services):
    """Committed space with ai_opt_in + owner cookie (jobs need real rows)."""
    from app import db
    from app.models.spaces import Space

    cookie = await login_as(committed_client, memory_services, "ai-owner@example.com")
    themes = await committed_client.get("/v1/themes", cookies={"ml_session": cookie})
    theme_id = next(t for t in themes.json()["data"] if t["plan_required"] == "free")["id"]
    data = await create_space(committed_client, cookie, theme_id, title="AI Space")
    space_id = data["space"]["id"]
    async with db.session_scope() as session:
        space = await session.get(Space, uuid.UUID(space_id))
        space.ai_opt_in = True
    raw = next(link for link in data["guest_links"]
               if link["token"]["role_cap"] == "contributor")["url"].split("guest=")[1]
    return {"cookie": cookie, "space_id": space_id, "guest": raw}


async def _post_text(committed_client, space_id, cookie, body, **overrides):
    payload = {"kind": "message", "body": body, "guest_name": "Zed"}
    payload.update(overrides)
    response = await committed_client.post(f"/v1/spaces/{space_id}/contributions",
                                           json=payload, cookies={"ml_session": cookie})
    assert response.status_code in (200, 201, 202), response.text
    return response.json()["data"]


async def _upload_ready(committed_client, cookie, space_id, data, mime, kind):
    from app.services.storage import get_storage

    presigned = await committed_client.post(
        "/v1/media/presign",
        json={"space_id": space_id, "mime": mime, "bytes": len(data), "kind": kind},
        cookies={"ml_session": cookie})
    asset_id = presigned.json()["data"]["id"]
    from app import db

    async with db.session_scope() as session:
        asset = await session.get(MediaAsset, uuid.UUID(asset_id))
        key = asset.original_key
    await get_storage().write_bytes(key, data, mime)
    confirmed = await committed_client.post("/v1/media/confirm", json={"asset_id": asset_id},
                                            cookies={"ml_session": cookie})
    assert confirmed.status_code == 202, confirmed.text
    return asset_id


async def _run_job(committed_client, cookie, space_id, kind, inputs):
    response = await committed_client.post(
        f"/v1/spaces/{space_id}/ai/jobs", json={"kind": kind, "inputs": inputs},
        cookies={"ml_session": cookie})
    assert response.status_code == 202, response.text
    job_id = response.json()["data"]["id"]
    job = await committed_client.get(f"/v1/ai/jobs/{job_id}", cookies={"ml_session": cookie})
    return job.json()["data"]


async def test_summary_success_and_privacy(committed_client, studio_space):
    cookie, space_id = studio_space["cookie"], studio_space["space_id"]
    await _post_text(committed_client, space_id, cookie, "Sunny picnic day")
    await _post_text(committed_client, space_id, cookie, "Secret note",
                     is_private_to_owner=True)
    job = await _run_job(committed_client, cookie, space_id, "summary", {})
    assert job["status"] == "succeeded"
    assets = await committed_client.get(f"/v1/spaces/{space_id}/ai/assets?kind=summary",
                                        cookies={"ml_session": cookie})
    assert len(assets.json()["data"]) == 1
    assert "joyful" in assets.json()["data"][0]["text_body"]
    # Originals untouched.
    listed = await committed_client.get(f"/v1/spaces/{space_id}/contributions",
                                        cookies={"ml_session": cookie})
    assert len(listed.json()["data"]) == 2


async def test_categorization_writes_labels(committed_client, studio_space):
    from app import db

    cookie, space_id = studio_space["cookie"], studio_space["space_id"]
    item = await _post_text(committed_client, space_id, cookie, "Family dinner")
    job = await _run_job(committed_client, cookie, space_id, "categorization", {})
    assert job["status"] == "succeeded"
    async with db.session_scope() as session:
        row = await session.get(Contribution, uuid.UUID(item["id"]))
        assert row.ai_categories == ["family", "celebration"]


@needs_ffmpeg
async def test_transcription_success(committed_client, studio_space):
    cookie, space_id = studio_space["cookie"], studio_space["space_id"]
    asset_id = await _upload_ready(committed_client, cookie, space_id, wav_bytes(),
                                   "audio/wav", "audio")
    job = await _run_job(committed_client, cookie, space_id, "transcription",
                         {"asset_ids": [asset_id]})
    assert job["status"] == "succeeded"
    assets = await committed_client.get(f"/v1/spaces/{space_id}/ai/assets?kind=transcription",
                                        cookies={"ml_session": cookie})
    assert "transcript" in assets.json()["data"][0]["text_body"].lower()


@needs_ffmpeg
async def test_captions_success(committed_client, studio_space):
    cookie, space_id = studio_space["cookie"], studio_space["space_id"]
    asset_id = await _upload_ready(committed_client, cookie, space_id, png_bytes(),
                                   "image/png", "image")
    job = await _run_job(committed_client, cookie, space_id, "captions",
                         {"asset_ids": [asset_id]})
    assert job["status"] == "succeeded"


async def test_permissions_and_opt_in(committed_client, memory_services, studio_space):
    from app import db
    from app.models.spaces import Space

    cookie, space_id, guest = (studio_space["cookie"], studio_space["space_id"],
                               studio_space["guest"])
    denied = await committed_client.post(
        f"/v1/spaces/{space_id}/ai/jobs", json={"kind": "summary", "inputs": {}},
        headers={"Authorization": f"Bearer {guest}"})
    assert denied.status_code == 403
    async with db.session_scope() as session:
        space = await session.get(Space, uuid.UUID(space_id))
        space.ai_opt_in = False
    off = await committed_client.post(f"/v1/spaces/{space_id}/ai/jobs",
                                      json={"kind": "summary", "inputs": {}},
                                      cookies={"ml_session": cookie})
    assert off.status_code == 403


async def test_quota_enforcement(committed_client, studio_space, monkeypatch):
    from app.config import reset_settings_cache

    cookie, space_id = studio_space["cookie"], studio_space["space_id"]
    monkeypatch.setenv("FREE_MONTHLY_AI_TOKENS", "1")
    reset_settings_cache()
    try:
        response = await committed_client.post(
            f"/v1/spaces/{space_id}/ai/jobs", json={"kind": "summary", "inputs": {}},
            cookies={"ml_session": cookie})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "quota_exceeded"
    finally:
        reset_settings_cache()


async def test_edit_promote_delete_asset(committed_client, studio_space):
    cookie, space_id = studio_space["cookie"], studio_space["space_id"]
    await _post_text(committed_client, space_id, cookie, "Something to summarize")
    await _run_job(committed_client, cookie, space_id, "summary", {})
    assets = await committed_client.get(f"/v1/spaces/{space_id}/ai/assets",
                                        cookies={"ml_session": cookie})
    asset_id = assets.json()["data"][0]["id"]

    edited = await committed_client.patch(f"/v1/ai/assets/{asset_id}",
                                          json={"title": "Edited", "text_body": "New words"},
                                          cookies={"ml_session": cookie})
    assert edited.json()["data"]["title"] == "Edited"
    promoted = await committed_client.post(f"/v1/ai/assets/{asset_id}/promote",
                                           cookies={"ml_session": cookie})
    assert promoted.json()["data"]["is_promoted"] is True
    assert promoted.json()["data"]["is_ai_labeled"] is True
    deleted = await committed_client.delete(f"/v1/ai/assets/{asset_id}",
                                            cookies={"ml_session": cookie})
    assert deleted.status_code == 204


async def test_retry_then_success_and_dead(committed_client, studio_space):
    from app.services.ai.providers import AIProvider

    class Flaky:
        name = "flaky"

        def __init__(self, failures: int):
            self.failures = failures
            self.calls = 0

        async def complete_text(self, system, user, **kwargs):
            self.calls += 1
            if self.calls <= self.failures:
                raise AIError("boom", retryable=True)
            return AIResult(text="Recovered.", input_tokens=5, output_tokens=5, model="flaky")

        async def complete_vision(self, *args, **kwargs):
            raise AIError("no vision", retryable=False)

        async def transcribe(self, *args, **kwargs):
            raise AIError("no audio", retryable=False)

    cookie, space_id = studio_space["cookie"], studio_space["space_id"]
    await _post_text(committed_client, space_id, cookie, "Retry me")
    set_ai_provider(Flaky(2))
    try:
        job = await _run_job(committed_client, cookie, space_id, "summary", {})
        assert job["status"] == "succeeded"
    finally:
        reset_ai_provider()
    set_ai_provider(Flaky(99))
    try:
        job = await _run_job(committed_client, cookie, space_id, "summary", {})
        assert job["status"] == "dead"
        assert "boom" in (job["last_error"] or "")
    finally:
        reset_ai_provider()


async def test_cancel_queued_job(committed_client, studio_space):
    from app import db
    from app.models.enums import AIJobStatus, AIKind
    from app.models.users import User

    cookie, space_id = studio_space["cookie"], studio_space["space_id"]
    async with db.session_scope() as session:
        owner = (await session.execute(
            select_user_by_email("ai-owner@example.com"))).scalar_one()
        job = AIGenerationJob(space_id=uuid.UUID(space_id), requested_by=owner.id,
                              kind=AIKind.summary, inputs={}, provider="fake",
                              status=AIJobStatus.queued, attempts=0,
                              idempotency_key=f"cancel-{uuid.uuid4().hex}",
                              quota_reserved=4000)
        session.add(job)
        await session.flush()
        job_id = str(job.id)
    cancelled = await committed_client.post(f"/v1/ai/jobs/{job_id}/cancel",
                                            cookies={"ml_session": cookie})
    assert cancelled.json()["data"]["status"] == "cancelled"
    quota = await committed_client.get(f"/v1/spaces/{space_id}/ai/quota",
                                       cookies={"ml_session": cookie})
    assert quota.json()["data"]["reserved"] == 0


def select_user_by_email(email: str):
    from sqlalchemy import select

    from app.models.users import User

    return select(User).where(User.email == email)


async def test_letter_and_book_keepsakes(committed_client, studio_space):
    cookie, space_id = studio_space["cookie"], studio_space["space_id"]
    await _post_text(committed_client, space_id, cookie, "The day we met")
    letter = await _run_job(committed_client, cookie, space_id, "letter",
                            {"to": "Ada", "tone": "warm"})
    assert letter["status"] == "succeeded"
    book = await _run_job(committed_client, cookie, space_id, "book",
                          {"title": "Our Story",
                           "sections": [{"title": "Beginnings"}]})
    assert book["status"] == "succeeded"
    assets = await committed_client.get(f"/v1/spaces/{space_id}/ai/assets",
                                        cookies={"ml_session": cookie})
    kinds = {asset["kind"] for asset in assets.json()["data"]}
    assert {"letter", "book"} <= kinds
    # Originals untouched; nothing auto-published.
    assert all(asset["is_promoted"] is False for asset in assets.json()["data"])


@needs_ffmpeg
async def test_highlight_film_renders(committed_client, studio_space):
    cookie, space_id = studio_space["cookie"], studio_space["space_id"]
    first = await _upload_ready(committed_client, cookie, space_id, png_bytes(),
                                "image/png", "image")
    second = await _upload_ready(committed_client, cookie, space_id, mp4_bytes(),
                                 "video/mp4", "video")
    job = await _run_job(committed_client, cookie, space_id, "highlight_film",
                         {"asset_ids": [first, second], "max_duration_s": 10})
    assert job["status"] == "succeeded"
    assets = await committed_client.get(
        f"/v1/spaces/{space_id}/ai/assets?kind=highlight_film",
        cookies={"ml_session": cookie})
    film = assets.json()["data"][0]
    assert film["asset_id"]
    assert film["edit_list"] and film["edit_list"]["clips"]
    media = await committed_client.get(f"/v1/media/{film['asset_id']}",
                                       cookies={"ml_session": cookie})
    assert media.json()["data"]["status"] == "ready"


async def test_highlight_film_honest_when_empty(committed_client, studio_space):
    cookie, space_id = studio_space["cookie"], studio_space["space_id"]
    missing = str(uuid.uuid4())
    response = await committed_client.post(
        f"/v1/spaces/{space_id}/ai/jobs",
        json={"kind": "highlight_film", "inputs": {"asset_ids": [missing]}},
        cookies={"ml_session": cookie})
    assert response.status_code == 202
    job = await committed_client.get(f"/v1/ai/jobs/{response.json()['data']['id']}",
                                     cookies={"ml_session": cookie})
    assert job.json()["data"]["status"] == "dead"
    assert "not found" in (job.json()["data"]["last_error"] or "").lower()


async def test_quota_endpoint_numbers(committed_client, studio_space):
    cookie, space_id = studio_space["cookie"], studio_space["space_id"]
    await _post_text(committed_client, space_id, cookie, "Count me")
    await _run_job(committed_client, cookie, space_id, "summary", {})
    quota = await committed_client.get(f"/v1/spaces/{space_id}/ai/quota",
                                       cookies={"ml_session": cookie})
    body = quota.json()["data"]
    assert body["used"] > 0 and body["limit"] > 0 and "resets_at" in body


async def test_openrouter_provider_mapping():
    import httpx

    from app.config import Settings
    from app.services.ai.providers import AIError, OpenRouterProvider

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/auth/" in path:
            return httpx.Response(401, json={})
        if "/limited/" in path:
            return httpx.Response(429, json={})
        if "/down/" in path:
            return httpx.Response(500, json={})
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2}})

    transport = httpx.MockTransport(handler)
    base = Settings(ai_provider="openrouter", openrouter_api_key="k",
                    openrouter_base_url="http://x")
    async with httpx.AsyncClient(transport=transport) as client:
        provider = OpenRouterProvider(base, client)
        ok = await provider.complete_text("s", "u", json_mode=False, max_tokens=10)
        assert (ok.text, ok.total_tokens) == ("hi", 5)

        async def call(path: str):
            provider._settings = Settings(
                ai_provider="openrouter", openrouter_api_key="k",
                openrouter_base_url=f"http://x/{path}")
            try:
                await provider.complete_text("s", "u", json_mode=False, max_tokens=10)
            finally:
                provider._settings = base

        for path, retryable in (("auth", False), ("limited", True), ("down", True)):
            try:
                await call(path)
                raise AssertionError(f"{path} should fail")
            except AIError as exc:
                assert exc.retryable is retryable, path

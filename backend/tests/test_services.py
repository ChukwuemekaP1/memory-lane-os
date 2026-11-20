"""Memory-backend service tests (async; no external services needed)."""

import time

import pytest

from app.services.jobs import MemoryJobRunner, job, registered_jobs
from app.services.mail import MemoryMailer, Message
from app.services.otp_store import MemoryOtpStore, OtpRecord
from app.services.ratelimit import MemoryRateLimiter
from app.services.storage import FilesystemStorage


async def test_memory_mailer_outbox_and_lookup():
    mailer = MemoryMailer()
    await mailer.send(Message(to="A@x.com", subject="s", text_body="b"))
    await mailer.send(Message(to="b@x.com", subject="s", text_body="b"))
    assert mailer.last_to("a@X.com").subject == "s"
    assert mailer.last_to("missing@x.com") is None
    mailer.clear()
    assert mailer.outbox == []


async def test_memory_otp_store_save_load_consume():
    store = MemoryOtpStore()
    record = OtpRecord(email="u@x.com", code_hash="c", magic_hash="m", attempts=0,
                       expires_at=0)
    await store.save(record, 60)
    assert (await store.load_by_magic("m")).email == "u@x.com"
    assert (await store.load_by_email("U@X.com")).magic_hash == "m"
    assert await store.bump_attempts("m") == 1
    await store.consume("m")
    assert await store.load_by_magic("m") is None
    assert await store.load_by_email("u@x.com") is None


async def test_memory_otp_store_expiry():
    store = MemoryOtpStore()
    record = OtpRecord(email="u@x.com", code_hash="c", magic_hash="m", attempts=0,
                       expires_at=0)
    await store.save(record, 60)
    record.expires_at = time.time() - 1  # force expiry
    assert await store.load_by_magic("m") is None
    assert await store.bump_attempts("m") is None


async def test_memory_rate_limiter_window():
    limiter = MemoryRateLimiter()
    assert (await limiter.check("k", 2, 60)).allowed
    assert (await limiter.check("k", 2, 60)).allowed
    denied = await limiter.check("k", 2, 60)
    assert not denied.allowed
    assert denied.retry_after_seconds >= 1
    assert (await limiter.check("other", 2, 60)).allowed


async def test_memory_job_runner_defers_until_drain():
    from app.services.jobs import drain_memory_jobs, reset_job_runner

    @job("test_probe_unique_xyz")
    async def _probe(payload):
        _probe.seen.append(payload)

    _probe.seen = []
    runner = MemoryJobRunner()
    job_id = await runner.enqueue("test_probe_unique_xyz", {"a": 1}, "idem-1")
    assert job_id.startswith("memory-")
    assert _probe.seen == []  # buffered, not executed
    import app.services.jobs as jobs_mod

    jobs_mod._runner = runner
    try:
        await drain_memory_jobs()
    finally:
        reset_job_runner()
    assert _probe.seen == [{"a": 1}]
    with pytest.raises(Exception):
        await runner.enqueue("no_such_job", {}, "idem-2")
    assert "test_probe_unique_xyz" in registered_jobs()


async def test_filesystem_storage_roundtrip(tmp_path):
    storage = FilesystemStorage(str(tmp_path))
    key = "originals/space/asset/photo.jpg"
    assert not await storage.exists(key)
    await storage.put_bytes(key, b"bytes-here")
    assert await storage.exists(key)
    assert await storage.size(key) == 10
    put_url = await storage.presign_put(key, "image/jpeg", 100, 60)
    get_url = await storage.presign_get(key, 60)
    assert put_url.startswith("file://") and get_url.startswith("file://")
    assert await storage.delete_prefix("originals/space") == 1
    assert not await storage.exists(key)


async def test_filesystem_storage_rejects_traversal(tmp_path):
    storage = FilesystemStorage(str(tmp_path))
    with pytest.raises(ValueError):
        await storage.put_bytes("../escape.txt", b"x")

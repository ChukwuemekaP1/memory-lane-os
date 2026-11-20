"""Background jobs: eager in-process runner (dev/tests) / ARQ (prod).

Job functions register with @job("name") and receive a single JSON payload
dict. Enqueue calls carry an idempotency key; the memory runner executes
inline, the ARQ runner defers to Redis-backed workers (app.worker).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from app.config import Settings
from app.errors import AppError
from app.logging import get_logger

logger = get_logger(__name__)

JobFunc = Callable[[dict[str, Any]], Awaitable[None]]
_REGISTRY: dict[str, JobFunc] = {}


def job(name: str) -> Callable[[JobFunc], JobFunc]:
    def decorator(func: JobFunc) -> JobFunc:
        if name in _REGISTRY:
            raise ValueError(f"duplicate job name: {name}")
        _REGISTRY[name] = func
        return func

    return decorator


def registered_jobs() -> dict[str, JobFunc]:
    return dict(_REGISTRY)


class JobRunner(Protocol):
    async def enqueue(self, name: str, payload: dict[str, Any], idempotency_key: str) -> str:
        """Queue a job. Returns a job id."""
        ...


class MemoryJobRunner:
    """Deferred-eager runner for dev/tests: enqueue buffers the job and
    `drain_memory_jobs` executes the buffer after the surrounding
    transaction commits (called by session teardown). Execution errors are
    logged, not raised — mirroring async workers where enqueue succeeds
    and the job row records the failure.
    """

    def __init__(self) -> None:
        self.enqueued: list[tuple[str, dict[str, Any], str]] = []
        self.pending: list[tuple[str, dict[str, Any]]] = []

    async def enqueue(self, name: str, payload: dict[str, Any], idempotency_key: str) -> str:
        if name not in _REGISTRY:
            raise AppError("internal_error", f"Unknown job: {name}.", 500)
        self.enqueued.append((name, payload, idempotency_key))
        self.pending.append((name, payload))
        return f"memory-{len(self.enqueued)}"


_draining = False


async def drain_memory_jobs() -> None:
    """Execute buffered memory jobs (post-commit). Reentrancy-safe."""
    global _draining
    if _draining:
        return
    runner = _runner
    if not isinstance(runner, MemoryJobRunner) or not runner.pending:
        return
    _draining = True
    try:
        while runner.pending:
            name, payload = runner.pending.pop(0)
            func = _REGISTRY.get(name)
            if func is None:  # pragma: no cover (enqueue already validated)
                continue
            try:
                await func(payload)
            except Exception:
                logger.exception("memory job failed: %s", name)
    finally:
        _draining = False


class ArqJobRunner:
    """Redis-backed runner. Importing arq lazily keeps dev/test installs lean."""

    def __init__(self, settings: Settings) -> None:
        if not settings.redis_url:
            raise ValueError("jobs_driver=arq requires redis_url")
        try:
            from arq import create_pool
            from arq.connections import RedisSettings
        except ImportError as exc:
            raise RuntimeError(
                "arq is not installed; install the api dependencies to run workers"
            ) from exc
        self._create_pool = create_pool
        self._redis_settings = RedisSettings.from_dsn(settings.redis_url)
        self._pool = None

    async def _get_pool(self):  # type: ignore[no-untyped-def]
        if self._pool is None:
            self._pool = await self._create_pool(self._redis_settings)
        return self._pool

    async def enqueue(self, name: str, payload: dict[str, Any], idempotency_key: str) -> str:
        if name not in _REGISTRY:
            raise AppError("internal_error", f"Unknown job: {name}.", 500)
        pool = await self._get_pool()
        job = await pool.enqueue_job(
            "run_registered_job", {"name": name, "payload": payload}, _job_id=idempotency_key
        )
        logger.info("enqueued job %s", name)
        return str(job.job_id)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None


async def run_registered_job(ctx: dict[str, Any], job_payload: dict[str, Any]) -> None:
    """ARQ entry point: dispatches to the in-process registry by name."""
    name = job_payload["name"]
    func = _REGISTRY.get(name)
    if func is None:
        raise AppError("internal_error", f"Unknown job: {name}.", 500)
    await func(job_payload["payload"])


_runner: JobRunner | None = None


def get_job_runner(settings: Settings | None = None) -> JobRunner:
    global _runner
    if _runner is not None:
        return _runner
    from app.config import get_settings

    resolved = settings or get_settings()
    _runner = ArqJobRunner(resolved) if resolved.jobs_driver == "arq" else MemoryJobRunner()
    return _runner


def reset_job_runner() -> None:
    global _runner
    _runner = None


@job("send_email")
async def send_email_job(payload: dict[str, Any]) -> None:
    from app.services.mail import Message, get_mailer

    message = Message(
        to=payload["to"],
        subject=payload["subject"],
        text_body=payload.get("text_body", ""),
        html_body=payload.get("html_body", ""),
        template=payload.get("template", ""),
    )
    await get_mailer().send(message)


@job("noop_ping")
async def noop_ping(payload: dict[str, Any]) -> None:
    logger.info("ping job ran (idempotency=%s)", payload.get("note", "-"))
    await asyncio.sleep(0)

"""ARQ worker entrypoint: `python -m app.worker` (compose `worker` service).

Runs the registered job functions against Redis, plus the schedule ticker
every minute. `--tick-once` runs a single due-event sweep and exits (dev).
"""

from __future__ import annotations

import sys

from app.config import get_settings
from app.logging import configure_logging
from app.services.jobs import registered_jobs, run_registered_job

# Import side-effects: register every job function with the runner.
import app.modules.archives.jobs  # noqa: F401 (build_archive, purge_user)
import app.modules.media.processing  # noqa: F401 (process_media)
import app.modules.scheduling.executor  # noqa: F401 (schedule_tick)
import app.modules.spaces.service  # noqa: F401 (purge_space)
import app.modules.studio.jobs  # noqa: F401 (ai_run)
import app.services.jobs  # noqa: F401 (send_email, noop_ping)


async def _tick(ctx: dict) -> None:
    from app.modules.scheduling.executor import run_due_events

    await run_due_events()


def worker_settings() -> dict:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    from arq.connections import RedisSettings
    from arq.cron import cron

    return {
        "redis_settings": RedisSettings.from_dsn(settings.redis_url),
        "functions": [run_registered_job],
        "cron_jobs": [cron(_tick, minute=set(range(60)), run_at_startup=False)],
        "job_names": set(registered_jobs()),
    }


class WorkerSettings:
    """ARQ CLI convention: `arq app.worker.WorkerSettings`."""

    def __new__(cls):  # type: ignore[no-untyped-def]
        return worker_settings()


if __name__ == "__main__":
    if "--tick-once" in sys.argv:
        import asyncio

        from app import db

        async def _once() -> None:
            from app.modules.scheduling.executor import run_due_events

            db.init_engine(get_settings())
            try:
                done = await run_due_events()
                print(f"tick done: {len(done)} event(s) executed")
            finally:
                await db.dispose_engine()

        asyncio.run(_once())
    else:
        from arq import run_worker

        run_worker(worker_settings())

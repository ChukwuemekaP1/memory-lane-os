"""Pytest bootstrap: env defaults, PG gating, app + service fixtures.

Execution tiers (honest by construction):
- Sync tests always run (pure logic, DDL compile, migration SQL render).
- Async tests need an event loop; sandboxes without socketpair skip them
  with ASYNCIO_SKIP_REASON instead of failing.
- needs_pg tests additionally require a reachable PostgreSQL; otherwise
  they skip with PG_SKIP_REASON. CI runs everything.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
from collections.abc import AsyncIterator, Iterator

import pytest

ASYNCIO_SKIP_REASON = "event loop unavailable in this environment (asyncio needs socketpair)"
PG_SKIP_REASON = "PostgreSQL unreachable (set TEST_DATABASE_URL; CI provides it)"

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("MAIL_DRIVER", "memory")
os.environ.setdefault("STORAGE_DRIVER", "filesystem")
os.environ.setdefault("JOBS_DRIVER", "memory")
os.environ.setdefault("AI_PROVIDER", "fake")
os.environ.setdefault("AI_RETRY_BASE_SECONDS", "0")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://memorylane:memorylane@127.0.0.1:5432/memorylane")
os.environ.setdefault("TEST_DATABASE_URL", os.environ["DATABASE_URL"].replace("/memorylane", "/memorylane_test"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _loops_work() -> bool:
    try:
        loop = asyncio.new_event_loop()
    except OSError:
        return False
    try:
        loop.close()
    except Exception:
        pass
    return True


LOOPS_WORK = _loops_work()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if LOOPS_WORK:
        return
    skipper = pytest.mark.skip(reason=ASYNCIO_SKIP_REASON)
    for item in items:
        func = getattr(item, "function", None) or getattr(item, "obj", None)
        if func is not None and inspect.iscoroutinefunction(func):
            item.add_marker(skipper)


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


async def _create_test_database(url: str) -> None:
    """CREATE DATABASE for the test URL via the maintenance database."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    base, _, db_name = url.rpartition("/")
    if not db_name or not db_name.replace("_", "").isalnum():
        raise ValueError(f"cannot parse database name from TEST_DATABASE_URL: {url!r}")
    maintenance = f"{base}/postgres"
    engine = create_async_engine(maintenance, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
async def pg_engine():
    """Session engine, migrated to head. Skips when PG is unreachable.

    Creates the test database on first use (connecting to the maintenance
    `postgres` database), so CI and fresh Compose stacks need no manual step.
    """
    from sqlalchemy.exc import ProgrammingError
    from sqlalchemy.ext.asyncio import create_async_engine

    url = os.environ["TEST_DATABASE_URL"]
    engine = create_async_engine(url)
    try:
        async with engine.connect():
            pass
    except ProgrammingError as exc:
        if "does not exist" not in str(exc.orig or exc):
            await engine.dispose()
            pytest.skip(PG_SKIP_REASON)
        await engine.dispose()
        await _create_test_database(url)
        engine = create_async_engine(url)
        try:
            async with engine.connect():
                pass
        except Exception:
            await engine.dispose()
            pytest.skip(PG_SKIP_REASON)
    except Exception:
        await engine.dispose()
        pytest.skip(PG_SKIP_REASON)
    # Migrate via Alembic API against the test database.
    from alembic import command
    from alembic.config import Config

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "alembic"))
    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        await asyncio.to_thread(command.upgrade, cfg, "head")
    finally:
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(pg_engine) -> AsyncIterator:
    """Function-scoped session wrapped in a rolled-back transaction.

    Buffered memory jobs drain at teardown (DB-backed jobs no-op since the
    rows roll back; mail jobs execute — that is what auth tests assert).
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.jobs import drain_memory_jobs

    async with pg_engine.connect() as connection:
        transaction = await connection.begin()
        sess = AsyncSession(connection, expire_on_commit=False,
                            join_transaction_mode="create_savepoint")
        try:
            yield sess
        finally:
            await drain_memory_jobs()
            await sess.close()
            await transaction.rollback()


@pytest.fixture
def memory_services():
    """Fresh in-memory service singletons for route/service tests."""
    from app.services.jobs import reset_job_runner
    from app.services.mail import MemoryMailer, reset_mailer
    from app.services.otp_store import MemoryOtpStore, reset_otp_store
    from app.services.ratelimit import MemoryRateLimiter, reset_rate_limiter

    reset_mailer()
    reset_otp_store()
    reset_rate_limiter()
    reset_job_runner()
    import app.services.jobs as jobs_mod
    import app.services.mail as mail_mod
    import app.services.otp_store as otp_mod
    import app.services.ratelimit as rl_mod

    mail_mod._mailer = MemoryMailer()
    otp_mod._otp_store = MemoryOtpStore()
    rl_mod._rate_limiter = MemoryRateLimiter()
    jobs_mod._runner = jobs_mod.MemoryJobRunner()
    yield {
        "mailer": mail_mod._mailer,
        "otp_store": otp_mod._otp_store,
        "limiter": rl_mod._rate_limiter,
        "jobs": jobs_mod._runner,
    }
    reset_mailer()
    reset_otp_store()
    reset_rate_limiter()
    reset_job_runner()


@pytest.fixture
async def client(session, memory_services, pg_engine):
    """ASGI test client with DB session + memory services wired in.

    Route sessions come from the rolled-back `session` fixture, while the
    real engine is initialized (against the test DB) so /readyz exercises
    the true startup path.
    """
    from httpx import ASGITransport, AsyncClient

    from app import db
    from app.config import Settings
    from app.db import get_session
    from app.main import create_app

    db.init_engine(Settings(database_url=os.environ["TEST_DATABASE_URL"]))
    app = create_app()

    async def _override_session() -> AsyncIterator:
        yield session

    async def _drain_after_response(response) -> None:
        from app.services.jobs import drain_memory_jobs

        await drain_memory_jobs()

    app.dependency_overrides[get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                           event_hooks={"response": [_drain_after_response]}) as http:
        yield http
    app.dependency_overrides.clear()
    await db.dispose_engine()


@pytest.fixture
async def committed_client(pg_engine, memory_services):
    """ASGI client whose requests COMMIT (for worker-executed job tests).

    Leaked rows are scoped per test (fresh spaces/users) so other tests'
    assertions are unaffected. Prefer `client` unless the test asserts on
    background-job effects (media processing, purge execution).
    """
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

    from app import db
    from app.config import Settings
    from app.db import get_session
    from app.main import create_app
    from app.services.jobs import drain_memory_jobs

    db.init_engine(Settings(database_url=os.environ["TEST_DATABASE_URL"]))
    app = create_app()
    owned = AsyncSession(pg_engine, expire_on_commit=False)

    async def _override_session() -> AsyncIterator:
        yield owned
        await owned.commit()
        await drain_memory_jobs()

    async def _drain_after_response(response) -> None:
        await drain_memory_jobs()

    app.dependency_overrides[get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                           event_hooks={"response": [_drain_after_response]}) as http:
        yield http
    app.dependency_overrides.clear()
    await owned.close()
    await db.dispose_engine()


@pytest.fixture
async def bare_client():
    """ASGI client without DB overrides (for /healthz)."""
    from httpx import ASGITransport, AsyncClient

    from app import db
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    await db.dispose_engine()


@pytest.fixture
def seed_ids() -> Iterator[dict[str, str]]:
    """Stable UUIDs for fixture rows (readable, deterministic)."""
    yield {
        "user": "10000000-0000-0000-0000-000000000001",
        "user2": "10000000-0000-0000-0000-000000000002",
        "theme": "10000000-0000-0000-0000-000000000003",
        "space": "10000000-0000-0000-0000-000000000004",
        "token": "10000000-0000-0000-0000-000000000005",
    }


@pytest.fixture
async def theme_row(session, seed_ids):
    from app.models.spaces import Theme

    theme = Theme(
        id=seed_ids["theme"], slug="test-theme", name="Test Theme", occasions=["birthday"],
        tokens={"accent": "#000"}, plan_required="free", is_active=True,
    )
    session.add(theme)
    await session.flush()
    return theme


@pytest.fixture
async def user_row(session, seed_ids):
    from app.models.users import User

    user = User(
        id=seed_ids["user"], email="owner@example.com", display_name="Owner",
        role_global="user", locale="en", timezone="Africa/Lagos", marketing_opt_in=False,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
async def space_row(session, seed_ids, user_row, theme_row):
    from app.models.spaces import Space, SpaceSettings

    space = Space(
        id=seed_ids["space"], owner_id=user_row.id, title="Test Space", occasion="birthday",
        theme_id=theme_row.id, visibility="link", contribution_policy="link_contributors",
        moderation_mode="post", allow_anonymous=True, allow_viewer_react=False,
        ai_opt_in=False, storage_quota_bytes=1_000_000, storage_used_bytes=0,
    )
    session.add(space)
    await session.flush()  # populate space.id (Python-side uuid7 default)
    session.add(SpaceSettings(space_id=space.id, reminder_enabled=True,
                              reminder_days_before=[7, 1], digest_enabled=True,
                              letter_delivery_timezone="Africa/Lagos",
                              default_reply_notify=True))
    await session.flush()
    return space

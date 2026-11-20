"""Database engine, session factory, and transaction helpers.

One async engine per process (built from Settings). Request handlers receive
an `AsyncSession` via `get_session`; the session commits on success and rolls
back on error. `session_scope()` is the same pattern for workers/scripts.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _split_ssl(url: str) -> tuple[str, bool]:
    """Strip ssl/sslmode query params (Neon-style) into a boolean.

    asyncpg wants `ssl=True`, not libpq-style `sslmode=require` strings, so
    the params are removed from the URL and returned as a flag instead.
    """
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    use_ssl = False
    kept = []
    for key, value in query:
        if key.lower() in ("ssl", "sslmode") and value.lower() in (
                "require", "verify-full", "verify-ca", "true", "1"):
            use_ssl = True
        else:
            kept.append((key, value))
    clean = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept),
                        parts.fragment))
    return clean, use_ssl


def _connect_args(url: str) -> dict[str, Any]:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    if "asyncpg" in url:
        # Never prepare statements implicitly (works behind pgbouncer, incl.
        # Neon's pooled endpoint) + opt-in TLS for managed providers.
        _, use_ssl = _split_ssl(url)
        args: dict[str, Any] = {"statement_cache_size": 0}
        if use_ssl:
            args["ssl"] = True
        return args
    return {}


def init_engine(settings: Settings) -> AsyncEngine:
    global _engine, _session_factory
    if _engine is not None:
        return _engine
    database_url = settings.database_url
    if "asyncpg" in database_url:
        database_url, _ = _split_ssl(database_url)
    kwargs: dict[str, Any] = {"connect_args": _connect_args(settings.database_url)}
    if not database_url.startswith("sqlite"):
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_pool_max_overflow
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 240
    _engine = create_async_engine(database_url, **kwargs)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Engine not initialized; call init_engine(settings) at startup.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Session factory not initialized; call init_engine(settings) at startup.")
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield a session that commits on clean exit, rolls back on error.

    Memory-driver jobs buffered during the request run after a successful
    commit (never on rollback), mirroring async worker semantics.
    """
    from app.services.jobs import drain_memory_jobs

    session = get_session_factory()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    else:
        await drain_memory_jobs()
    finally:
        await session.close()


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request with commit/rollback."""
    async with session_scope() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None

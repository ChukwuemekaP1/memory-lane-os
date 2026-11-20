"""Ensure the PostgreSQL database from DATABASE_URL exists (create if missing).

Used by scripts/dev.ps1 and local setup. Exits 0 when the database is
reachable, 2 with a human-readable message otherwise (no tracebacks).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from urllib.parse import unquote, urlparse


def parse_database_url(url: str) -> dict[str, str | int]:
    if "+" in url.split("://", 1)[0]:
        url = url.split("+", 1)[0] + "://" + url.split("://", 1)[1]
    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgres"):
        raise ValueError(f"only postgresql:// URLs are supported, got: {parsed.scheme}")
    dbname = (parsed.path or "").lstrip("/")
    if not dbname or not dbname.replace("_", "").isalnum():
        raise ValueError(f"cannot parse database name from URL (check DATABASE_URL): {url!r}")
    return {
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 5432,
        "user": unquote(parsed.username or "postgres"),
        "password": unquote(parsed.password or ""),
        "dbname": dbname,
    }


async def ensure_database(parts: dict[str, str | int], timeout: float) -> str:
    import asyncpg

    maintenance = dict(parts)
    maintenance["dbname"] = "postgres"
    try:
        conn = await asyncio.wait_for(asyncpg.connect(**maintenance), timeout)
    except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
        raise SystemExit(
            f"PostgreSQL is not reachable at {parts['host']}:{parts['port']}.\n"
            "Start your local PostgreSQL service or fix DATABASE_URL in .env, "
            "then re-run."
        ) from None
    except Exception as exc:  # asyncpg.InvalidPasswordError etc.
        message = str(exc).lower()
        if "password" in message or "auth" in message:
            raise SystemExit(
                f"PostgreSQL rejected the credentials for user '{parts['user']}'.\n"
                "Put the right password in DATABASE_URL in .env, then re-run."
            ) from None
        raise SystemExit(f"Could not connect to PostgreSQL: {exc}") from None
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", parts["dbname"])
        if not exists:
            await conn.execute(f'CREATE DATABASE "{parts["dbname"]}"')
            return "created"
        return "exists"
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure the app database exists.")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    if not args.database_url:
        print("DATABASE_URL is not set (and no --database-url given).")
        return 2
    try:
        parts = parse_database_url(args.database_url)
    except ValueError as exc:
        print(exc)
        return 2
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        print("asyncpg is not installed; run: pip install -e .  (inside backend/.venv)")
        return 2
    try:
        result = asyncio.run(ensure_database(parts, args.timeout))
    except SystemExit as exc:
        print(exc.code)
        return 2
    print(f"database '{parts['dbname']}' {result} "
          f"({parts['user']}@{parts['host']}:{parts['port']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Neon/database preflight: inspect a live database and compare with the app schema.

Usage (networked machine with credentials):
    python backend/scripts/neon_db_preflight.py --database-url "$DATABASE_URL"

Exit 0 when the database matches the models exactly; exit 2 with a drift
report otherwise. Read-only: issues SELECTs only, never writes.
"""

from __future__ import annotations

import argparse
import asyncio
import sys


def compare_schemas(expected_tables: set[str], actual_tables: set[str],
                    expected_enums: set[str], actual_enums: set[str]) -> dict:
    """Pure diff core (unit-tested offline)."""
    missing_tables = sorted(expected_tables - actual_tables)
    extra_tables = sorted(actual_tables - expected_tables - {"alembic_version", "spatial_ref_sys"})
    missing_enums = sorted(expected_enums - actual_enums)
    return {
        "missing_tables": missing_tables,
        "extra_tables": extra_tables,
        "missing_enums": missing_enums,
        "matches": not missing_tables and not missing_enums,
    }


async def inspect_database(url: str, timeout: float) -> dict:
    import asyncpg

    if "+asyncpg://" in url:
        url = url.replace("+asyncpg", "", 1)
    try:
        conn = await asyncio.wait_for(asyncpg.connect(url, timeout=timeout), timeout + 5)
    except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
        raise SystemExit(f"Unreachable database host in URL (timeout {timeout}s).")
    except Exception as exc:
        raise SystemExit(f"Could not connect: {exc}")
    try:
        version = await conn.fetchval("SHOW server_version")
        dbname = await conn.fetchval("SELECT current_database()")
        tables = {row[0] for row in await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
        enums = {row[0] for row in await conn.fetch(
            "SELECT typname FROM pg_type WHERE typtype = 'e'")}
        alembic_version = None
        if "alembic_version" in tables:
            alembic_version = await conn.fetchval("SELECT version_num FROM alembic_version")
        counts = {}
        for table in ("users", "spaces", "contributions", "media_assets"):
            if table in tables:
                counts[table] = await conn.fetchval(f"SELECT count(*) FROM {table}")
        return {"version": version, "database": dbname, "tables": tables,
                "enums": enums, "alembic_version": alembic_version, "counts": counts}
    finally:
        await conn.close()


def expected_schema() -> tuple[set[str], set[str]]:
    import app.models  # noqa: F401
    from app.models.base import Base
    from sqlalchemy.orm import configure_mappers

    configure_mappers()
    tables = set(Base.metadata.tables)
    enum_names: set[str] = set()
    for table in Base.metadata.tables.values():
        for column in table.columns:
            column_type = column.type
            name = getattr(column_type, "name", None)
            if name and column_type.__class__.__name__ == "Enum":
                enum_names.add(name)
    return tables, enum_names


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare a live DB with app models.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    import os

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    expected_tables, expected_enums = expected_schema()
    try:
        live = asyncio.run(inspect_database(args.database_url, args.timeout))
    except SystemExit as exc:
        print(exc.code)
        return 2
    report = compare_schemas(expected_tables, live["tables"], expected_enums, live["enums"])
    print(f"server: PostgreSQL {live['version']}  database: {live['database']}")
    print(f"alembic_version: {live['alembic_version'] or '(none — fresh database)'}")
    print(f"tables: {len(live['tables'])} found, {len(expected_tables)} expected")
    if live["counts"]:
        print("row counts: " + ", ".join(f"{k}={v}" for k, v in live["counts"].items()))
    if report["matches"] and not report["extra_tables"]:
        print("MATCH: database matches the application schema exactly.")
        return 0
    if report["missing_tables"]:
        print("missing tables: " + ", ".join(report["missing_tables"]))
    if report["missing_enums"]:
        print("missing enums: " + ", ".join(report["missing_enums"]))
    if report["extra_tables"]:
        print("extra tables (left untouched): " + ", ".join(report["extra_tables"]))
    if report["matches"]:
        print("OK to migrate: all expected objects exist (extras preserved).")
        return 0
    print("DRIFT: run `alembic upgrade head` against this database, then re-run.")
    return 2


if __name__ == "__main__":
    sys.exit(main())

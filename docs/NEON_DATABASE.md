# Memory Lane — Neon Database Runbook (Phase 2)

How the app schema gets onto Neon PostgreSQL: branch strategy, preflight,
apply, verify, rollback. All commands below run on a networked machine with
`neon login` completed — they cannot run in an offline sandbox.

## 1. Branch strategy (never touch production first)

```powershell
# Authenticate once (browser sign-in)
neon login

# Create the integration branch from production (copy-on-write, instant)
neon branches create --project-id plain-rice-42859459 --name dev --parent production

# Point the shell at it and fetch its connection string
neon checkout dev   # or: --project-id ... per command; also pulls branch
                    # env vars (DATABASE_URL, ...) into local .env by default
neon connection-string dev --pooled   # API use (pooler)
neon connection-string dev            # direct (migrations)
```

Destructive or experimental work happens on `dev` (or short-lived clones)
only. Production receives migrations after dev verification, via this same
runbook, with approval.

## 2. Preflight: inspect before changing anything

```powershell
$env:DATABASE_URL = 'postgresql+asyncpg://USER:PASS@HOST/db?sslmode=require'
cd backend
.venv/Scripts/python scripts/neon_db_preflight.py --database-url $env:DATABASE_URL
```

The script is read-only. It prints server version, `alembic_version`
(`(none — fresh database)` on empty branches), table/enum counts, row
counts for core tables, and a diff against the 26 app tables + 30 enums:

- `MATCH` → nothing to do (or extras listed, which are preserved).
- `missing tables/enums` → proceed to §3, then re-run (exit 0 expected).
- Nonzero exit always explains itself; it never writes.

## 3. Apply with the project's migration framework

```powershell
cd backend
$env:DATABASE_URL = '<direct (unpooled) dev URL, asyncpg scheme, ?sslmode=require>'
.venv/Scripts/python -m alembic upgrade head
```

Rules enforced by review, not just trust:

- One Alembic chain (currently 0001–0006); every migration reversible.
- Additive only on shared branches: new tables/columns/indexes; no drops,
  no renames, no data rewrites. Anything destructive gets its own approved
  plan with a backup first.
- Seeds are idempotent (`ON CONFLICT DO NOTHING`).
- `neon_auth` schema is Neon-managed: the app never creates auth tables —
  linkage is `users.neon_auth_sub` only (migration 0006).

## 4. Verify after applying

```powershell
# 1. Preflight must now report MATCH.
.venv/Scripts/python scripts/neon_db_preflight.py --database-url $env:DATABASE_URL

# 2. Point the test suite at a scratch database on the same branch and run it:
$env:TEST_DATABASE_URL = '<same host, db=memorylane_test>'
.venv/Scripts/python -m pytest tests/ -q
```

Fresh-database proof (already executed 2026-11-18 on PG 16.15): the full
0001–0006 SQL applies to an empty database with zero errors → 27 tables
(26 + `alembic_version`), 30 enums, 9 seeded themes, `alembic_version=0006`.

## 5. Promote to production (with approval only)

1. Re-run §2 against the production branch; confirm the diff is exactly the
   expected migrations.
2. Take a Neon backup/restore point (Neon console: instant restore).
3. Apply §3 against production during a maintenance window.
4. Re-run §2 + a smoke subset (`pytest tests/test_health.py` + login flow).
5. Rollback = Neon point-in-time restore to the pre-migration point (plus
   `alembic downgrade` only for additive, data-safe reversals).

## 6. Rules compliance map

| Brief rule | Implementation |
|---|---|
| Neon Auth owns `neon_auth` | no auth tables in app migrations; `users.neon_auth_sub` link only |
| No recreated passwords/sessions | sessions stay in `user_sessions`; no password columns anywhere |
| Owner identity from verified identity | `require_user`/actor resolution; request-supplied IDs never trusted |
| DB access server-side | frontend talks only to the FastAPI API (same-origin `/api` proxy) |
| AuthZ on every private operation | `SpaceContext` + capability predicates on all space routes |
| Preserve records, no destructive migrations | additive chain; purge paths are explicit, confirmed, job-run |

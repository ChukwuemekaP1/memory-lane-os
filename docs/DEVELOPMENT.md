# Memory Lane — Development Guide

How to run, configure, test, and debug the stack locally.

## 1. Prerequisites

- Python 3.12 (backend targets `>=3.12`)
- Node 24 (frontend)
- Docker + Compose (recommended path — runs Postgres/Redis/MinIO/Mailpit), or:
- Local PostgreSQL 16+ and optionally Redis 7+ for the no-Docker path

## 2. Environment

```bash
cp .env.example .env   # then edit secrets/ports as needed
```

Key variables (all documented in `.env.example`):

| Variable | Purpose | Local default |
|---|---|---|
| `DATABASE_URL` | API database | Compose Postgres |
| `TEST_DATABASE_URL` | Pytest database (auto-created) | `memorylane_test` |
| `REDIS_URL` | Queues/OTP/rate-limit; empty = memory backends | Compose Redis |
| `STORAGE_DRIVER` | `filesystem` (dev) or `s3` (compose/prod) | `filesystem` |
| `MAIL_DRIVER` | `file` (dev), `memory` (tests), `smtp` (compose/prod) | `file` |
| `JOBS_DRIVER` | `memory` (eager) or `arq` (workers) | `memory` |

Backend settings fail fast on invalid config (bad DB scheme, insecure
cookies outside local/test). The frontend talks to the API through the
same-origin `/api` proxy (see `frontend/next.config.ts`) so session cookies
work with `SameSite=Lax`; point-to-API deployments need cookie-domain
alignment instead.

## 3. Running with Compose (recommended)

```bash
docker compose up --build
```

Services and addresses:

| Service | Address |
|---|---|
| Web | http://localhost:3000 |
| API (`/healthz`, `/readyz`, `/docs`) | http://localhost:8000 |
| Mailpit UI / SMTP | http://localhost:8025 / 127.0.0.1:1025 |
| MinIO API / console | http://localhost:9000 / :9001 |
| Postgres / Redis | 127.0.0.1:5432 / :6379 |

The `api` container runs `alembic upgrade head` on start; `minio-init`
creates the `memorylane-originals`/`memorylane-derivatives` buckets.
Sign-in codes and magic links land in Mailpit.

## 4. Running without Docker

```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows PowerShell
pip install -e ".[dev]"
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000

# Worker (second shell; needs REDIS_URL + JOBS_DRIVER=arq)
python -m app.worker

# Frontend (third shell)
cd frontend
npm install
npm run dev
```

Notes:

- Without Redis, leave `REDIS_URL` empty: OTP, rate-limit, and jobs use
  in-memory backends (single-process dev only).
- Without MinIO, `STORAGE_DRIVER=filesystem` keeps bytes under `.devdata/`.
  Note: browser uploads need S3-compatible storage (compose/MinIO) because
  browsers cannot PUT to `file://` presigned URLs — run compose for the
  contribute flow, or exercise uploads via the API tests.
- Dev mail lands as JSON files under `.devdata/mail` (`MAIL_DRIVER=file`).

## 5. Database

```bash
cd backend
python -m alembic upgrade head        # migrate up
python -m alembic downgrade -1        # roll back one
python -m alembic upgrade head --sql  # render SQL without a connection
python -m alembic revision -m "desc"  # new migration (review the diff!)
```

Conventions: one Alembic chain, every migration reversible, seeds as
idempotent data migrations. Models live in `backend/app/models/`; the
contract is [architecture/DATABASE_DESIGN.md](architecture/DATABASE_DESIGN.md).

## 6. Auth in dev

1. `POST /v1/auth/request-code {"email": "you@example.com"}` → 202.
2. Read the code + magic link from Mailpit (compose) or `.devdata/mail/*.json`.
3. `POST /v1/auth/verify {"email", "code"}` → session cookie, or open the
   magic link in a browser (302 to the app) / with `Accept: application/json`.
4. `GET /v1/auth/me` shows the current actor (user or guest).

Codes and magic links are single-use and expire after 10 minutes; 5 wrong
attempts invalidate a challenge.

## 7. Tests

```bash
cd backend
python -m pytest tests/                                  # full backend suite
python -m pytest tests/ -m "not needs_pg and not needs_redis"  # no services
python -m pytest tests/ --cov=app --cov-report=term-missing     # with coverage

cd frontend
npm test            # vitest unit tests
npm run typecheck   # tsc --noEmit
npm run build       # production build
npm run playwright  # browser smoke (starts `next dev` itself)
```

Tiers: sync unit tests always run; async tests need an event loop; `needs_pg`
needs PostgreSQL (`TEST_DATABASE_URL`, auto-created); `needs_redis` needs
Redis. Anything unavailable is *skipped with a reason*, never faked.

## 8. Lint and types

```bash
cd backend && ruff check app alembic tests && mypy app
cd frontend && npm run typecheck
```

## 9. Troubleshooting

- **Install fails offline:** both ecosystems need registry access on first
  install. Backend: `pip install -e ".[dev]"`. Frontend: `npm install`
  (commit the resulting `package-lock.json`, then CI switches to `npm ci`).
- **DB connection refused:** check Postgres is up and `DATABASE_URL` matches
  (compose uses host `postgres`, local dev uses `127.0.0.1`).
- **Magic link expired/consumed:** request a fresh code; links are single-use.
- **MinIO buckets missing:** `docker compose up minio-init` re-runs bucket setup.
- **Port clashes:** override `API_PORT`/`WEB_PORT`/`POSTGRES_PORT` in `.env`.

## 10. First networked run checklist

The repo ships without `package-lock.json` (it can only be generated with
registry access). On the first machine with network:

1. `cd frontend && npm install` → verify, then commit `package-lock.json`.
2. Switch CI frontend install to `npm ci`.
3. Run the full suites once and record results in `docs/PROJECT_STATUS.md`.

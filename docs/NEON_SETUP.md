# Memory Lane — Neon Setup

How this app runs on Neon (Postgres + object storage), and what is already
wired in code. The repo pins org `org-long-queen-89999463`, project
`plain-rice-42859459`, branch `production` (see `.neon`, written by
`neon init`).

## 1. Current state

Done in-repo:

- `.neon` — link context (org/project/branch pin, no secrets).
- `neon.ts` — service policy: Neon Auth enabled, one private `assets` bucket.
  Postgres is implicit (every branch has it).
- Root `package.json` — pins `@neon/config` 1.1.0 (needed to load `neon.ts`)
  and a root `npm run build` delegating to the frontend.
- Backend Neon readiness: `DATABASE_URL` accepts `?sslmode=require` /
  `?ssl=require` (translated to `ssl=True` for asyncpg in `app/db.py`);
  `statement_cache_size=0` keeps asyncpg safe behind Neon's pooled endpoint;
  Alembic already uses `NullPool`.

Not done (needs your terminal — network + browser sign-in):

- `neon login`, `neon deploy`, pulling live env vars, and end-to-end proof.

## 2. Finish setup (run on your machine, with network)

```powershell
# 1. Authenticate (browser sign-in opens; finish it there)
neon login

# 2. Install tooling deps (root) + frontend deps
npm install
npm --prefix frontend install

# 3. Provision/apply services from neon.ts, pull env into .env.local
neon deploy
```

If `neon deploy` reports drift or prompts, accept the `neon.ts` policy
(auth + `assets` bucket) unless you have reason to diverge.

## 3. Wire the pulled env vars into the app

`neon deploy` writes service credentials to `.env.local` (or `.env` if it
exists — this repo has `.env`, so expect values there). Map them:

| Neon-provided value | App variable | Notes |
|---|---|---|
| `DATABASE_URL` (pooled, `sslmode=require`) | backend `DATABASE_URL` | Change scheme to `postgresql+asyncpg://`, keep `?sslmode=require` |
| Direct (unpooled) URL, if shown | use for Alembic | Migrations prefer the direct endpoint |
| Object-storage endpoint | `S3_ENDPOINT_URL` | S3-compatible endpoint Neon prints |
| Bucket credentials | `S3_ACCESS_KEY` / `S3_SECRET_KEY` | least-privilege pair |
| `assets` bucket | `S3_BUCKET_ORIGINALS` **and** `S3_BUCKET_DERIVATIVES` | single Neon bucket; `originals/` + `derivatives/` prefixes separate areas (see `Storage._bucket_for`) |
| `STORAGE_DRIVER` | `s3` | switch off `filesystem` |
| Auth service keys | — | see §5, intentionally unwired |

## 4. Verify end to end

```powershell
# Backend against Neon Postgres
cd backend
$env:DATABASE_URL = '<neon pooled URL, postgresql+asyncpg scheme>'
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m pytest tests/ -q

# Frontend build (root entrypoint)
npm run build

# Smoke (two terminals or the VS Code tasks)
# Terminal 1: backend/.venv + uvicorn :8000 with Neon DATABASE_URL
# Terminal 2: frontend npm run dev, open http://localhost:3000
# Then: GET /healthz, POST /v1/auth/request-code, create a space,
# upload a file (lands in the Neon bucket), download it back.
```

## 5. Auth decision (deliberately unchanged)

This app ships complete native passwordless auth (OTP + magic links,
sessions, guest tokens). Neon's Auth service is provisioned by `neon.ts`
but **not wired in**: adopting it would replace the identity module, the
guest model, and the permissions matrix — a product decision, not a setup
step. Keep native auth unless that decision is made explicitly.

## 6. Driver notes (why this stack fits Neon)

- asyncpg + SQLAlchemy 2.x async; `statement_cache_size=0` disables implicit
  prepared statements, which is what PgBouncer-style poolers require.
- Alembic online runs use `NullPool` (no stale pooled connections).
- For very high connection churn, prefer Neon's pooled endpoint for the API
  and the direct endpoint for migrations.
- Never commit `.env` / `.env.local` (gitignored); rotate a leaked Neon
  credential from the Neon console, not by editing code.

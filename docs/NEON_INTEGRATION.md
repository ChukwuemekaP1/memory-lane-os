# Memory Lane — Neon Integration

Status: **Connected and live-verified on the `dev` branch** (`2026-11-19`). Production branch remains untouched pending explicit promotion approval.

## 1. Neon Project & Branch Topology

| Resource | Value | Notes |
|---|---|---|
| Organization | `org-long-queen-89999463` | Linked in `.neon` |
| Project | `memory-lane` (`plain-rice-42859459`) | AWS `us-east-2` |
| Development Branch | `dev` (`br-damp-truth-beh9ifs1`) | Parent: `production` (`br-wispy-lab-behh3sq3`), PostgreSQL `18.7`, TTL expires `2026-11-20T01:24:28Z` |
| Production Branch | `production` (`br-wispy-lab-behh3sq3`) | Primary/default branch — **untouched** during Phases 2–10 |

## 2. Connected Neon Services on `dev`

1. **Neon PostgreSQL (Database):**
   - Pooled API endpoint: `ep-shiny-fog-be5iot59-pooler.c-9.us-east-2.aws.neon.tech` (`DATABASE_URL`, `postgresql+asyncpg://...?ssl=require`, `statement_cache_size=0`).
   - Direct migration endpoint: `ep-shiny-fog-be5iot59.c-9.us-east-2.aws.neon.tech` (`DATABASE_URL_UNPOOLED`, `NullPool` in Alembic).
   - Schema: Alembic head `0007`, 26 application tables + `alembic_version`, 30 PostgreSQL enums, `neon_db_preflight.py` returns `MATCH`.
2. **Neon Managed Better Auth:**
   - Base URL: `https://ep-shiny-fog-be5iot59.neonauth.c-9.us-east-2.aws.neon.tech/neondb/auth`
   - JWKS URL: `https://ep-shiny-fog-be5iot59.neonauth.c-9.us-east-2.aws.neon.tech/neondb/auth/.well-known/jwks.json` (`EdDSA` / `Ed25519` OKP key)
   - Trusted domain configured: `http://localhost:3000`
   - Wired in Next.js 16 via `@neondatabase/auth` (`0.6.0-beta`) and verified server-side in FastAPI via `app/modules/identity/neon.py`.
3. **Neon Object Storage (S3-Compatible):**
   - Endpoint: `https://br-damp-truth-beh9ifs1.storage.c-9.us-east-2.aws.neon.tech` (`us-east-2`)
   - Private bucket provisioned: `assets` (`access: private`, per `neon.ts`)
   - S3v4 path-style presigned PUT/GET URLs verified live; unauthenticated direct access returns `403`.

## 3. Environment Configuration

Local secrets live exclusively in gitignored `.env` (backend) and `frontend/.env.local` (frontend). `backend/app/config.py` loads `(".env", "../.env")` and automatically maps Neon's `AWS_*` storage variables and `NEON_AUTH_BASE_URL` origin (`iss`/`aud`) into backend `Settings`.

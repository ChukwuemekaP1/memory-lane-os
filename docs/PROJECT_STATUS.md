# Memory Lane — Project Status & Production Readiness

Last updated: **2026-11-19** (Phases 2–11 completed on Neon `dev` branch).

## 1. Module & Integration Status

| Area | Status | Evidence |
|---|---|---|
| Neon PostgreSQL (`dev` branch `br-damp-truth-beh9ifs1`) | **Complete & Verified** | Alembic `0001`–`0007` applied; `neon_db_preflight.py` returns `MATCH` |
| Neon Managed Better Auth (Next.js + FastAPI JWKS) | **Complete & Verified** | `@neondatabase/auth` + `EdDSA` JWKS verification + profile sync + single-session enforcement |
| Neon Object Storage (`assets` private bucket) | **Complete & Verified** | S3v4 presigned PUT/GET, FFmpeg derivatives, `generated/` & `exports/` separation, `403` unauth denial, deletion |
| OpenRouter AI Studio & Centralized Job System | **Complete & Verified** | Text, vision, audio transcription, image gen, highlight film, token/USD cost tracking, idempotency, privacy filtering |
| Product Modules (Dashboard, Spaces, Guest Links, Gallery, Timeline, Themes, Moderation, Reactions/Replies, Scheduling, Notifications, Archives/Exports) | **Connected** | All routes use real Neon PostgreSQL + Neon Object Storage; FastAPI `_dep` wiring fixed across all routers |
| Frontend Build & Tests | **Passing** | `tsc --noEmit` (0 errors), `vitest run` (16/16 passed), `next build` (exit 0) |

## 2. Remaining Items Before Production Promotion

1. **Dev branch TTL:** Neon `dev` branch (`br-damp-truth-beh9ifs1`) has an automatic expiry of `2026-11-20T01:24:28Z`. Extend or remove TTL if continuing dev testing past that timestamp.
2. **Production deployment (requires explicit approval):**
   - Run `alembic upgrade head` (`0001`–`0007`) against `production` after taking a Neon restore point and verifying preflight diff.
   - Provision private `assets` bucket on `production` (`neon deploy --branch production`) and add the production frontend origin to Neon Auth trusted domains.
   - Configure production Redis (`REDIS_URL`, `JOBS_DRIVER=arq`) and real SMTP (`MAIL_DRIVER=smtp`) for background workers and email delivery at scale.
   - Initialize Git and commit changes before deploying.

## 3. Production Readiness Assessment

**Development environment (`dev`): Ready and end-to-end verified (9/9 live integration tests passed).**  
**Production environment (`production`): Intentionally untouched; ready for controlled promotion once the checklist in §2 (backup, Next.js security upgrade, production Redis/SMTP, and explicit approval) is completed.**

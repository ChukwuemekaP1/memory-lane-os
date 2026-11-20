# Memory Lane — Database Schema & Migrations

Target verified database: Neon `dev` branch (`br-damp-truth-beh9ifs1`, PostgreSQL `18.7 (a21afb5)`, database `neondb`).

## 1. Alembic Migration Chain (`0001` → `0007`)

| Revision | File | Purpose |
|---|---|---|
| `0001` | `0001_initial.py` | Core tables (users, sessions, spaces, themes, contributions, media, interactions, AI studio, archives, billing, usage) and PostgreSQL native enums |
| `0002` | `0002_seed.py` | Idempotent seed of 9 default themes (`ON CONFLICT (slug) DO NOTHING`); fixed missing `CAST(:id AS uuid)` for online SQLAlchemy/asyncpg execution |
| `0003` | `0003_spaces_evolution.py` | Space kinds, timezone, `public` visibility, contribution policies |
| `0004` | `0004_stage3.py` | AI categories on contributions, contribution tags (`contribution_tags`) |
| `0005` | `0005_personal_archives.py` | Personal archives & export lifecycle |
| `0006` | `0006_audit_auth_link.py` | `users.neon_auth_sub` unique linkage + `audit_events` table |
| `0007` | `0007_ai_studio_production.py` | Additive enum values (`ai_kind`: `image_generation`, `story_enhancement`; `usage_kind`: `ai_image`) + `input_tokens`, `output_tokens`, `cost_usd` (`Numeric(10,6)`) on `ai_generation_jobs` |

## 2. Schema Verification (`neon_db_preflight.py`)

- **Alembic head:** `0007 (head)`
- **Tables:** 27 found (26 application tables + `alembic_version`)
- **Enums:** 30 expected PostgreSQL native enums present
- **Result:** `MATCH: database matches the application schema exactly.` (exit code `0`)
- **Neon Auth isolation:** `neon_auth` schema is managed exclusively by Neon; application linkage is `users.neon_auth_sub` only.

# Memory Lane

A collaborative digital memory platform: create shared spaces for birthdays,
weddings, graduations, farewells, tributes, family memories, travel, and more —
invite people with a link or QR code, collect their messages, photos, videos,
and voice notes in one place, and turn them into something worth revisiting.

**Status:** development foundation + database + passwordless auth (no product
journeys yet). See [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md).

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 + TypeScript + Tailwind + shadcn-style UI |
| Backend | FastAPI modular monolith (Python 3.12) |
| Database | PostgreSQL 16 (SQLAlchemy + Alembic) |
| Workers | Redis-backed (ARQ) |
| Storage | S3-compatible (MinIO locally) |
| Tests | Pytest, Vitest, Playwright |

Architecture and contracts live in [docs/architecture/](docs/architecture/)
(system design, data flows, decisions, database, API, permissions).

## Quickstart (one command, Windows/VS Code)

Requirements: Python 3.12+, Node 20+, and a running local PostgreSQL
(put its password in `DATABASE_URL` in `.env`). First run needs network
for `pip`/`npm` installs.

Open a PowerShell terminal in VS Code at the project root and run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
```

This checks prerequisites, creates `backend/.venv`, installs dependencies,
creates the database, runs migrations, installs frontend packages, then opens
the API (port 8000) and web app (port 3000) in two new windows. Re-running is
safe. Then open http://localhost:3000 in your browser. Close the two windows
to stop. (In VS Code you can also run the task `dev: setup + run all` via
Ctrl+Shift+P → "Tasks: Run Task".)

Dry run without changing anything:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -CheckOnly
```

## Quickstart (Docker Compose, alternative)

Needs Docker Desktop. Gives you Postgres, Redis, MinIO, and Mailpit too:

```bash
cp .env.example .env
docker compose up --build
```

Then open:

- Web app: http://localhost:3000
- API health: http://localhost:8000/healthz
- API docs: http://localhost:8000/docs
- Mailpit (dev email): http://localhost:8025
- MinIO console: http://localhost:9001

Sign-in codes and magic links arrive via Mailpit in compose, or as JSON files
under `backend/.devdata/mail/` with the one-command script.

## Local development (no Docker)

Prerequisites: Python 3.12, Node 24, PostgreSQL 16, optionally Redis.

```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/activate  # Windows; use source .venv/bin/activate on Linux/macOS
pip install -e ".[dev]"
python -m alembic upgrade head
python -m uvicorn app.main:app --reload  # http://localhost:8000

# Frontend (second shell)
cd frontend
npm install
npm run dev  # http://localhost:3000
```

Full guide (env vars, services, testing, troubleshooting):
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Tests

```bash
cd backend && python -m pytest tests/      # API + DB + auth suite
cd frontend && npm test                     # Vitest unit tests
cd frontend && npm run playwright           # Browser smoke (needs dev server)
```

CI runs lint (ruff), typecheck (mypy/tsc), migrations, the full suites, and
Compose image builds on every push/PR.

## Project layout

```text
backend/      FastAPI app (app/), Alembic migrations, Pytest suite
frontend/     Next.js app (App Router), Vitest + Playwright
docs/         Audit, status, architecture, API + DB contracts, dev guide
docker-compose.yml  Local Postgres/Redis/MinIO/Mailpit/API/worker/web
```

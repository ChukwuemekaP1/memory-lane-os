# Memory Lane — AI Memory Studio

Status: **Connected to live OpenRouter + Neon PostgreSQL + Neon Object Storage and end-to-end verified** (`2026-11-19`).

## 1. Centralized Job Architecture

All AI operations execute through a single centralized service layer (`backend/app/modules/studio/service.py`, `backend/app/modules/studio/jobs.py`, `backend/app/services/ai/providers.py`) — no competing AI clients or job systems:

- **Authorization & privacy:** Staff-only (`owner`/`collaborator`), space `ai_opt_in=true` required, asset ownership verified against `space_id`, and `is_private_to_owner=true` / `pending` / `hidden` / `rejected` contributions are **always excluded** from AI inputs.
- **Persistence & reliability:** Persistent `AIGenerationJob` states (`queued`, `running`, `succeeded`, `failed`, `dead`, `cancelled`), `started_at`/`finished_at`, inline retries with exponential backoff, idempotency keys, token reservation & usage recording (`usage_records`), and actual `model`, `input_tokens`, `output_tokens`, `cost_usd` persisted per job.
- **Frontend integration (`frontend/components/studio-view.tsx`):** Queries `GET /v1/spaces/{id}/ai/capabilities` to show configured models or explicit unavailability reasons (never simulating results), polls active jobs every 3s so browser refreshes never lose jobs, displays real model/token/cost metadata, links signed downloads for generated media, and requires explicit owner approval (`promote`) before publishing AI outputs.

## 2. Connected Studio Capabilities

| Capability | Endpoint / Kind | Model / Engine | Live Status |
|---|---|---|---|
| Capability discovery | `GET /v1/spaces/{id}/ai/capabilities` | Server config | Live-verified |
| Memory summary | `POST /v1/spaces/{id}/ai/jobs` (`summary`) | `deepseek/deepseek-v4.1-flash` | Live-verified |
| Smart categorization | `categorization` | `deepseek/deepseek-v4.1-flash` (JSON) | Live-verified |
| Caption & image analysis | `captions` | `deepseek/deepseek-v4.1-flash` (vision JSON) | Live-verified |
| Voice note transcription | `transcription` | `google/gemini-2.5-flash-lite` (audio) | Live-verified |
| Memory letter | `letter` | `deepseek/deepseek-v4.1-flash` | Live-verified |
| Digital memory book | `book` + `POST /v1/spaces/{id}/archives` (`book_pdf`) | `deepseek/deepseek-v4.1-flash` (JSON) + archive worker | Live-verified (`book_pdf` premium-gated `403` on free plan) |
| Story enhancement | `story_enhancement` | `deepseek/deepseek-v4.1-flash` (JSON) | Implemented & wired |
| Artwork generation | `image_generation` | `google/gemini-3.1-flash-image` → Neon Object Storage | Live-verified |
| Highlight film | `highlight_film` | `deepseek/deepseek-v4.1-flash` + FFmpeg → Neon Object Storage | Live-verified |
| Job history & cancel | `GET …/ai/jobs`, `GET /v1/ai/jobs/{id}`, `POST …/cancel` | PostgreSQL | Live-verified |
| Asset review lifecycle | `GET …/ai/assets`, `PATCH`, `POST …/promote`, `DELETE` | PostgreSQL | Live-verified |

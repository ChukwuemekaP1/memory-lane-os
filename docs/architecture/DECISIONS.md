# Memory Lane — Architecture Decisions (ADRs)

Date: 2026-11-17
Stage: Stage 1 — Discovery and System Design, Prompt 03
Design only — no application code exists or was changed.

Format: one record per decision (context → decision → consequences).
Supersede by appending a new record, never by rewriting history.

## ADR-001: Modular monolith, not microservices

- **Context:** Greenfield repo (see [project audit](../PROJECT_AUDIT.md)):
  no code, no team-scaling pressure, no proven hot spots. The brief
  explicitly prefers a modular monolith unless a concrete requirement
  justifies otherwise.
- **Decision:** One FastAPI deployment + worker processes sharing one
  codebase and one Postgres database, with the 13 modules in
  [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) as hard package
  boundaries (own routes/services/models; cross-module via service layer).
- **Consequences:** Simple deploys, single migration chain, in-process
  calls (no network failure modes between modules). If one module later
  needs independent scaling (likely candidates: media workers, AI
  workers), it can be extracted behind its service interface — workers
  already run as separate processes, so that path is open.

## ADR-002: Stack as briefed (Next.js/TS + FastAPI + Postgres)

- **Context:** The brief names Next.js + TypeScript + Tailwind + shadcn/ui,
  FastAPI + SQLAlchemy + Alembic + PostgreSQL. Nothing in the audit
  contradicts this.
- **Decision:** Adopt the stack as-is. Next.js App Router (SSR share pages,
  client components for interactive surfaces); SQLAlchemy 2.x async;
  Alembic single migration chain.
- **Consequences:** Mainstream hiring, mature docs, container-friendly.
  Revisit only if Prompt 04 surfaces a need the stack cannot meet.

## ADR-003: Redis-backed workers via ARQ

- **Context:** Need async media/AI/notify/schedule/export processing.
  Candidates: Celery (heavy, sync-first), RQ (sync), ARQ (asyncio-native).
- **Decision:** Redis as broker + ARQ as the worker library behind a thin
  internal `jobs` wrapper (enqueue/status/cancel) so it can be swapped.
  Five queues (`media/ai/notify/schedule/export`) with per-queue
  concurrency; idempotency keys + backoff + dead-letter rows everywhere.
- **Consequences:** Fits FastAPI's async model with minimal ops overhead.
  Redis is disposable by design: all durable intent lives in Postgres, so
  queue loss degrades to re-enqueue, never data loss.

## ADR-004: S3-compatible storage with presigned direct upload

- **Context:** Mobile photo/video/voice uploads must survive slow networks
  (Nigeria/Africa/global), and the API must not become a byte proxy.
- **Decision:** Bytes live in S3-compatible storage (`originals/` immutable,
  `derivatives/` generated). Browsers upload/download directly via
  short-lived presigned URLs; the API handles metadata + authorization +
  quotas only. Local dev uses MinIO; production uses a managed
  S3-compatible vendor chosen on cost (see ADR-009). CDN caches derivatives.
- **Consequences:** API stays light; multipart/resumable uploads possible;
  no public buckets — every URL is minted per authorized request.

## ADR-005: Passwordless auth for accounts, unguessable tokens for guests

- **Context:** Owners need secure accounts without password friction;
  guests must contribute with zero signup (core product loop).
- **Decision:** Email OTP + magic link (either verifies), hashed single-use
  codes, rotating sessions. Guests get per-space revocable tokens
  (expiry, max-uses, role cap) carried in share links/QR; anonymous
  contributions attach to the token. Identical auth responses for unknown
  emails (no account oracle).
- **Consequences:** No passwords to breach; guest flow stays one-tap.
  Token revocation/expiry + rate limits + optional pre-moderation are the
  abuse backstop and must ship with the first guest release, not later.

## ADR-006: Authorization enforced server-side via a permissions module

- **Context:** Roles span owner/collaborator/identified + anonymous
  contributor/viewer/admin across private, link-only, and scheduled spaces.
- **Decision:** A dedicated `permissions` module is the single enforcement
  point; every route declares its requirement; UI hiding is cosmetic only.
  App-layer checks (not Postgres RLS) keep policy in one testable place.
- **Consequences:** Permission changes are one-module edits covered by
  Pytest; frontend cannot escalate by calling APIs directly.

## ADR-007: AI behind a provider abstraction, OpenRouter default

- **Context:** AI features (transcription → highlight films) are
  cost-sensitive, privacy-sensitive, and provider-volatile.
- **Decision:** Internal `AIProvider` interface (text/vision/transcription);
  OpenRouter as the default route; all AI runs are quota-checked,
  per-space opt-in jobs producing first-class, labeled, deletable assets.
  Prefer transcripts/derivatives over original bytes in prompts.
- **Consequences:** Providers swap without touching features; spend is
  capped by plan quotas; privacy story (what leaves, retention) is
  documented once at the abstraction boundary.

## ADR-008: DB-backed due-queue scheduling, not cron-fired logic

- **Context:** Reveals, capsules, future letters, and reminders must fire
  exactly once, timezone-aware, surviving restarts.
- **Decision:** `scheduled_events` rows in Postgres with UTC `run_at` +
  idempotency keys; a 1-minute ticker claims due rows
  (`FOR UPDATE SKIP LOCKED`) and enqueues real work. Restart catch-up is
  automatic; double-fire is impossible by key.
- **Consequences:** Slight (≤1 min) fire-time granularity, acceptable for
  celebrations; no reliance on host cron semantics in production.

## ADR-009: Affordable-hosting defaults, env-swapped

- **Context:** Brief demands affordable dev/deploy and global (esp.
  Nigerian/African) accessibility; audit left infra open.
- **Decision:** Local = Docker Compose (web, api, workers, Postgres,
  Redis, MinIO, Mailpit). Production starts on a container-compatible
  host (single host or PaaS) with managed Postgres/Redis where affordable,
  else the same Compose topology on one VM with backups. Email via an
  SMTP-compatible transactional provider; billing via Paystack (Africa:
  cards/bank/mobile money) + Stripe (international) behind one interface.
  Exact vendors are env/config, not code.
- **Consequences:** Day-one costs stay low; scaling = bigger host, then
  managed services, then split workers — each step without rewrites.

## ADR-010: Quotas and entitlements enforced with permissions

- **Context:** Free/premium plans, storage + AI quotas, premium themes,
  one-time purchases must be tamper-proof.
- **Decision:** `billing` resolves entitlements; enforcement happens at the
  same checkpoints as authZ (presign, AI enqueue, theme select, export).
  Webhooks are signature-verified and idempotent. Downgrade/past-due never
  deletes memories — it blocks new premium usage after grace.
- **Consequences:** No free bypass via direct API calls; billing disputes
  can't cause data loss.

## ADR-011: Realtime via polling first, SSE as the upgrade path

- **Context:** The live celebration wall needs freshness, but websockets
  add infra (sticky sessions, connection state) a launch doesn't need.
- **Decision:** Short-polling for the wall at launch; SSE later if load or
  UX demands it. No websocket infrastructure.
- **Consequences:** Works on every host and flaky network; revisit with
  real usage numbers.

## ADR-012: Testing and CI ship with the scaffold

- **Context:** Audit risk #9: agreed harnesses (Pytest/Vitest/Playwright)
  absent; unverified claims likely without them.
- **Decision:** The first implementation stage lands lint + typecheck +
  Pytest + Vitest + Playwright (critical journeys: auth, space create,
  guest contribute, reveal) plus a Compose smoke test — before features.
- **Consequences:** Every later stage can honestly report pass/fail;
  scaffolding takes longer up front, on purpose.

## ADR-013: Public visibility + space kind/timezone/overrides (schema evolution)

- **Context:** The brief's visibility set (`private`/`link`/`scheduled`) had
  no open-read option, and spaces lacked a kind taxonomy, an explicit
  timezone, and per-space theme customization.
- **Decision (migration 0003):** add `public` visibility (reads need no
  credential; writes stay credentialed; no discovery feed), `spaces.kind`
  (event/ongoing/personal/relationship/family/group/custom, CHECKed),
  `spaces.timezone` (IANA, drives reminder/reveal date math), and
  `spaces.theme_overrides` (JSONB token overrides; content/permissions
  untouched by theme changes).
- **Consequences:** Additive only; existing rows default safely
  (`kind=event`, owner-zone timezone, empty overrides).

## ADR-014: Stage II implementation notes (jobs, uploads, reports)

- **Deferred-eager jobs:** the memory job runner buffers jobs and executes
  them after the surrounding transaction commits (`drain_memory_jobs` in
  session teardown), instead of true-inline execution — so dev/test jobs
  see committed rows exactly like ARQ workers do.
- **Single-PUT uploads:** v1 uses one presigned PUT per file (video cap
  2 GB); multipart/resumable upload is a follow-up. Interrupted uploads
  retry whole-file; confirm verifies existence + size, and the worker
  records sha256 (stronger than the spec's client-hash sketch).
- **v1 reports:** `POST /contributions/{id}/report` notifies space staff
  by email; a persistent report queue with auto-hide thresholds is a
  follow-up (no schema churn for v1).
- **Replies follow posting rights** (`can_post`), clarifying the matrix
  Viewer-column ❌ for `anyone_with_link` spaces (see matrix note 8b).

## Open items for Prompt 04

1. Exact table/column shapes, indexes, and delete behaviors.
2. REST endpoint list with request/response schemas and error codes.
3. Full permissions matrix incl. edge cases (revoked token mid-upload,
   collaborator limits, pre- vs post-moderation).
4. Rate-limit budgets per endpoint class.
5. Production vendor picks (host, Postgres/Redis, S3-compatible, email)
   with priced options.

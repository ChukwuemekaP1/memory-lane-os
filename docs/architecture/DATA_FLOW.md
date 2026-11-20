# Memory Lane — Data Flow

Date: 2026-11-17
Stage: Stage 1 — Discovery and System Design, Prompt 03
Companion to [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md). Design only —
no application code exists or was changed.

## 1. How the frontend communicates with the backend

- **Protocol:** REST JSON over HTTPS. One typed client (`lib/api.ts`);
  every response uses the shared envelope (data + request id) and the
  shared error shape (code, message, retryable flag). Full request/response
  contracts, validation rules, pagination, and rate limits are specified in
  Prompt 04.
- **Auth on requests:** session cookie (HttpOnly, SameSite=Lax) for
  logged-in owners/collaborators; guest token as `Authorization: Bearer
  <guest-token>` (or cookie) for link/QR access. The API resolves
  *actor = user session OR guest token* on every request, then evaluates
  permissions before touching data.
- **Media bypass:** bytes never flow through the API. The API only mints
  presigned URLs and records metadata; browsers talk directly to
  S3-compatible storage (and the CDN for derivatives).
- **Long operations** (transcode, AI, exports, reveals) are asynchronous:
  the API returns a job id immediately; the client polls job status
  (backoff) and renders progress/empty/error/retry states. Nothing blocks
  a request handler on FFmpeg, AI providers, or email.

## 2. How background jobs are handled

```mermaid
flowchart LR
    API["API request handler"] -->|enqueue with idempotency key| RD[("Redis queues<br/>media/ai/notify/schedule/export")]
    RD --> WM["media workers<br/>(FFmpeg)"]
    RD --> WA["ai workers<br/>(provider calls)"]
    RD --> WN["notify workers<br/>(email)"]
    RD --> WS["schedule ticker<br/>(1/min due-claim)"]
    RD --> WE["export workers<br/>(ZIP/book/video)"]
    WM & WA & WN & WS & WE --> PG[("Postgres<br/>(job rows, state)")]
    WM & WE --> S3[("Object storage")]
    WA --> LLM["AI providers"]
    WN --> SMTP["Email provider"]
    WS -->|enqueue due work| RD
```

Rules:

1. Handlers validate, authorize, check quotas, write the intent row, and
   enqueue — then return. All heavy lifting happens in workers.
2. Every job carries an idempotency key; retries and double-delivery are
   safe by construction (DB unique constraints + conditional updates).
3. Attempts use exponential backoff; exhausted jobs land in a dead-letter
   row visible to admins with manual retry.
4. The scheduler never runs business logic on a tick: it claims due
   `scheduled_events` rows (`FOR UPDATE SKIP LOCKED`) and enqueues the
   actual work, so restarts and multi-worker deploys stay exactly-once.

## 3. Authentication flow (passwordless)

```mermaid
sequenceDiagram
    participant U as User (browser)
    participant A as API (identity)
    participant R as Redis (rate limit + code)
    participant N as notify worker
    participant E as Email provider

    U->>A: POST /auth/request-code {email}
    A->>R: check rate limit (email + IP)
    A->>R: store hashed OTP + magic token (TTL 10 min)
    A->>N: enqueue send-otp job
    N->>E: deliver code + magic link
    A-->>U: 202 accepted (no account-oracle: same response always)

    alt OTP code path
        U->>A: POST /auth/verify {email, code}
    else Magic link path
        U->>A: GET /auth/magic?token=...
    end
    A->>R: verify + single-use consume
    A->>A: create session (rotate refresh token)
    A-->>U: HttpOnly session cookie + profile
```

Notes: identical responses for unknown emails (no account enumeration);
codes are hashed at rest, single-use, and short-lived; sessions rotate
refresh tokens and support logout-everywhere.

## 4. Memory space creation flow

```mermaid
sequenceDiagram
    participant O as Owner (browser)
    participant A as API (spaces + billing)
    participant P as Postgres
    participant S as schedule worker (later)

    O->>A: POST /spaces {title, occasion, dates, theme, privacy}
    A->>A: auth: must be logged-in user
    A->>A: authorize plan limits (space count, premium theme?)
    A->>P: insert space + owner membership + settings
    A->>P: create guest tokens (viewer/contributor) + scheduled_events (reveal/reminders)
    A-->>O: 201 {space, shareLinks, qrPayload}
    Note over S: reveal/reminder events fire via Section 8
```

Validation (title, dates, theme entitlement, privacy enum) runs on both
client and server; the server is authoritative.

## 5. Guest contribution flow (no account required)

```mermaid
sequenceDiagram
    participant G as Guest (browser)
    participant A as API (contributions + media)
    participant P as Postgres
    participant O as Object storage (presigned)

    G->>A: GET /s/:id?guest=<token> — resolve space + permissions
    A->>P: validate token (revoked? expired? max-uses? role cap?)
    A-->>G: space view (theme, contribution policy)

    alt Text / story contribution
        G->>A: POST /contributions {token, body, name?}
        A->>A: authorize (token role + space policy + moderation mode)
        A->>P: insert contribution (pending if pre-moderation)
        A-->>G: 201 {contribution}
    else Media contribution
        G->>A: POST /media/presign {token, type, size}
        A->>A: authorize + quota check (space storage budget)
        A-->>G: {uploadUrl, assetId}
        G->>O: PUT bytes direct to storage
        G->>A: POST /media/confirm {assetId, contribution?}
        A->>P: register asset + contribution
        A->>A: enqueue media processing job
        A-->>G: 202 {asset, jobId} — client polls job status
    end
```

Abuse controls: per-token and per-IP rate limits, token revocation,
optional pre-moderation queue, size/type allowlists, EXIF location
stripped by default.

## 6. Media upload and processing flow

```mermaid
sequenceDiagram
    participant C as Client (owner or guest)
    participant A as API (media)
    participant P as Postgres
    participant Q as media queue (Redis)
    participant W as media worker (FFmpeg)
    participant S as Object storage

    C->>A: POST /media/presign {mime, bytes}
    A->>A: authorize + quota check
    A-->>C: {assetId, uploadUrl (TTL), maxBytes}
    C->>S: PUT original bytes (multipart for large video)
    C->>A: POST /media/confirm {assetId}
    A->>P: insert media_assets (status=uploaded) + media_processing_jobs
    A->>Q: enqueue transcode job (idempotency: assetId)
    A-->>C: 202 {jobId}

    Q->>W: deliver job
    W->>S: fetch original (never modifies it)
    W->>W: validate, strip EXIF location, FFmpeg renditions<br/>(image sizes, H.264/AAC, audio normalize, poster)
    W->>S: write derivatives/
    W->>P: update asset (status=ready, duration, dimensions)
    W-->>C: (client poll) ready → CDN-signed derivative URLs
```

Failure path: job retries with backoff; terminal failure marks the asset
`failed` with a user-safe reason and owner-visible diagnostics; the
original is retained for manual retry.

## 7. AI processing flow (AI Memory Studio)

```mermaid
sequenceDiagram
    participant O as Owner/Collaborator
    participant A as API (ai-studio + billing)
    participant P as Postgres
    participant Q as ai queue (Redis)
    participant W as ai worker
    participant V as AI provider (via abstraction)

    O->>A: POST /ai/jobs {spaceId, kind, inputs}
    A->>A: authorize (owner/collaborator) + space AI opt-in?
    A->>A: quota check (plan AI budget)
    A->>P: insert ai_generation_jobs (status=queued)
    A->>Q: enqueue (idempotency: jobId)
    A-->>O: 202 {jobId}

    Q->>W: deliver job
    W->>P: load inputs (prefer transcripts/derivatives over originals)
    W->>V: provider call (OpenRouter default; capped prompts)
    V-->>W: result
    W->>W: validate + persist ai_generated_assets<br/>(highlight film: AI edit list → FFmpeg render)
    W->>P: job status=succeeded/failed + usage_records row
    W-->>O: (client poll) preview → accept / regenerate / delete
```

All AI outputs are labeled AI-assisted in the UI; quota is reserved at
enqueue and settled (or refunded on failure) at completion.

## 8. Scheduled reveal flow (reveals, capsules, letters, reminders)

```mermaid
sequenceDiagram
    participant T as schedule ticker (1/min)
    participant P as Postgres (scheduled_events)
    participant Q as queues (Redis)
    participant W as workers (notify/schedule)
    participant U as Recipients

    T->>P: claim due rows (FOR UPDATE SKIP LOCKED, batch)
    P-->>T: due events [{id, kind, run_at, payload, idempotencyKey}]
    T->>Q: enqueue one job per event (key = id + version)
    Q->>W: deliver
    W->>P: mark running → execute (publish space / send letter / digest)
    W->>U: email / in-app notification
    W->>P: mark done (or retryable failure → backoff)
    Note over T: restart catch-up: overdue + unclaimed rows are picked up<br/>on the next tick; already-done keys are never re-run
```

Timezone correctness: `run_at` is stored in UTC with the originating
timezone recorded; reminder date math runs in the space's timezone.

## 9. Export and billing webhooks (summary)

- **Exports** (ZIP, book, video, data export): same async pattern as
  Section 7 — authorize owner, check plan, enqueue on `export` queue,
  build from originals (+ AI assets for books/film), upload result to
  storage, notify with a signed download link. Deletion flows hard-delete
  bytes + rows and write an audit record.
- **Billing webhooks** (Paystack/Stripe): verify signature → idempotent
  handler keyed by provider event id → update `subscriptions`/`payments` →
  enqueue receipt email. Duplicate deliveries are no-ops.

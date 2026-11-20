# Memory Lane — API Specification

Date: 2026-11-17
Stage: Stage 1 — Discovery and System Design, Prompt 04
Design only — no routes, schemas, or code exist or were changed.

Contracts for the REST API in [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md).
Entities: [DATABASE_DESIGN.md](DATABASE_DESIGN.md). Authorization per endpoint:
[PERMISSIONS_MATRIX.md](PERMISSIONS_MATRIX.md).

## 1. Global conventions

- **Base URL:** `https://api.memorylane.example/v1` (prod), `http://localhost:8000/v1`
  (Compose). All paths below are relative to `/v1`. **Versioning:** URL prefix;
  breaking changes bump to `/v2` with a 6-month overlap.
- **Format:** JSON, UTF-8. Times RFC 3339 UTC (`2026-11-17T12:30:00Z`).
  Ids are UUIDv7 strings. Money fields are `{amount_minor, currency}`.
- **Auth:** logged-in users send the session cookie (`ml_session`, HttpOnly,
  SameSite=Lax, Secure in prod). Guests send
  `Authorization: Bearer <guest-token>` (raw 256-bit token, hex). Some
  guest GETs also accept `?guest=<token>` for plain `<a>`/QR flows; the API
  treats both identically and never logs the token.
- **Success envelope:** `{"data": <T>, "request_id": "<uuid>"}`.
  **List envelope:** `{"data": [...], "page": {...}, "request_id": "..."}`.
- **Validation:** server-side is authoritative (Pydantic v2 schemas mirroring
  every table constraint: lengths, enums, allowlists). Client validates for UX
  only. Unknown JSON fields are rejected (`extra="forbid"`) so typos fail loudly.
- **Content limits:** JSON bodies ≤ 1 MB; text fields per
  [DATABASE_DESIGN.md](DATABASE_DESIGN.md) maxima. Bytes never travel in JSON —
  media uses presigned URLs (Section 6).

## 2. Error response format

```json
{
  "error": {
    "code": "contribution_rejected",
    "message": "This space is not accepting contributions right now.",
    "retryable": false,
    "details": {"space_id": "…"},
    "request_id": "…"
  }
}
```

Standard codes (HTTP status in brackets):

| Code | Status | Meaning |
|---|---|---|
| `validation_error` | 422 | schema/field failure; `details.fields` lists `{field, reason}` |
| `unauthenticated` | 401 | no/invalid session or guest token |
| `forbidden` | 403 | authenticated but not permitted (see PERMISSIONS_MATRIX) |
| `not_found` | 404 | row missing — or hidden by permissions (same response, no oracle) |
| `conflict` | 409 | unique/idempotency/state conflict; `details` names the constraint |
| `gone` | 410 | token revoked, link expired, download expired |
| `quota_exceeded` | 403 | storage/AI/plan budget exhausted; `details.{limit,used}` |
| `rate_limited` | 429 | budget hit; `Retry-After` header set |
| `payload_too_large` | 413 | body or declared upload exceeds limits |
| `unsupported_media` | 415 | MIME not on the allowlist |
| `upstream_error` | 502 | AI/email/billing provider failed; `retryable: true` unless noted |
| `internal_error` | 500 | bug; `request_id` is the support key |

Rules: 4xx messages are user-safe and UI-renderable; 5xx/502 details stay
server-side. `not_found` doubles for "exists but you may not see it" so ids
and tokens cannot be probed.

## 3. Pagination, filtering, sorting

- **Cursor pagination** on all lists: `GET …?limit=&cursor=`.
  `limit` default 20, max 100. Response `page: {next_cursor, has_more}`.
  Cursors are opaque (created_at + id); stable under concurrent inserts.
- **Filtering:** exact-match params (`?kind=story&status=visible`),
  date ranges (`taken_from/taken_to`), full-text `q` (trigram search).
  Unknown params are ignored (forgiving reads, strict writes).
- **Sorting:** `?sort=-taken_at` (whitelisted fields only, `-` = desc);
  default per endpoint, documented below.

## 4. Rate limiting

Redis token buckets, per scope below. Limits are starting values, tunable
via env without code changes. All 429s carry `Retry-After`.

| Class | Key | Budget |
|---|---|---|
| OTP request | email + IP | 5 / 10 min |
| OTP verify / magic | email + IP | 10 / 10 min |
| Guest reads | token + IP | 300 / min |
| Guest writes (contrib/react/reply) | token + IP | 30 / min |
| Media presign | actor + space | 60 / min |
| AI enqueue | user | plan quota + 20 req / min |
| Exports | user | 5 / hour |
| Webhooks | provider IP allowlist + signature | 600 / min |
| Default authenticated | user | 600 / min |

## 5. Idempotency

- `POST /contributions`, `/media/confirm`, `/ai/jobs`, `/archives`,
  `/scheduled-events` accept `Idempotency-Key: <uuid>` (client-generated).
  Replays within 24 h return the original response (`200`, `replayed: true`
  header `Idempotent-Replayed: true`); different payload + same key → `409`.
- Keys map to the tables' `UNIQUE(…idempotency_key)` constraints — the DB is
  the backstop, not just the cache.
- Webhooks use provider event ids (see Section 11); duplicate deliveries
  return `200` with no side effects.

## 6. Authentication (`/auth`)

Actor: none (public, rate-limited).

| Method + path | Purpose | Request | Response |
|---|---|---|---|
| `POST /auth/request-code` | send OTP + magic link | `{email}` | `202 {masked_email}` — identical for unknown emails |
| `POST /auth/verify` | exchange code for session | `{email, code}` (6 digits) | `200 {user, session_expires_at}` + cookie |
| `GET /auth/magic?token=` | exchange magic link | query token (single-use, 10 min) | `302` to app + cookie, or `410` JSON for API clients |
| `POST /auth/refresh` | rotate session | cookie | `200 {session_expires_at}` + new cookie |
| `POST /auth/logout` | revoke this session | cookie | `204` |
| `POST /auth/logout-all` | revoke all sessions | cookie | `204` |
| `GET /auth/me` | current actor | session or guest token | `200 {actor: {type: user/guest, …}}` |

Validation: email RFC + max 254; code exactly 6 numeric; 5 attempts then
challenge invalidated. Recovery = re-verify email (no separate flow needed).

## 7. Spaces (`/spaces`)

Auth: session required except where noted. Permission details in
[PERMISSIONS_MATRIX.md](PERMISSIONS_MATRIX.md).

| Method + path | Purpose | Request | Response |
|---|---|---|---|
| `POST /spaces` | create space | `{title, description?, occasion, theme_id, visibility?, contribution_policy?, moderation_mode?, allow_anonymous?, ai_opt_in?, event_date?, publish_at?, location_label?}` | `201 {space, guest_links: [{label, role_cap, url}]}` |
| `GET /spaces` | owner's dashboard list | `?role=owner/collaborator/all&sort=&cursor=` | list of spaces with `stats {contributions, storage_used_bytes}` |
| `GET /spaces/{id}` | space detail (auth-aware view) | session or guest token | `200 {space, theme, my_permissions: [...]}` — 404 if invisible to actor |
| `PATCH /spaces/{id}` | edit settings | any mutable field (owner; collaborator: subset) | `200 {space}` |
| `DELETE /spaces/{id}` | soft-delete | — | `204` (recoverable 30 days) |
| `POST /spaces/{id}/restore` | undo soft-delete | — | `200 {space}` |
| `POST /spaces/{id}/purge` | hard-delete after grace | `{confirm_title}` must match title | `202 {purge_archive_id}` (async purge job) |
| `POST /spaces/{id}/transfer` | change owner | `{new_owner_user_id}` | `200 {space}` |
| `GET /spaces/{id}/settings` | notification/scheduling knobs | — | `200 {settings}` |
| `PATCH /spaces/{id}/settings` | update knobs | `{reminder_enabled?, reminder_days_before?, digest_enabled?, …}` | `200 {settings}` |
| `GET /themes` | theme catalog | `?occasion=` | `200 [{theme}]` with `entitled: bool` per plan |

Validation: `title` 1–120; `publish_at` must be future; premium `theme_id`
requires premium plan (`quota_exceeded` otherwise); `publish_at` in the past
via PATCH publishes immediately (creates no event; sets visibility).
Side effects of create: default contributor + viewer guest tokens, reveal
event if `publish_at` set, reminder events if `event_date` + reminders on.

## 8. Guest access, memberships, invitations

| Method + path | Purpose | Request | Response |
|---|---|---|---|
| `GET /spaces/{id}/guest-tokens` | list tokens (staff) | — | `200 [{id, label, role_cap, use_count, expires_at, revoked_at}]` — hashes never exposed |
| `POST /spaces/{id}/guest-tokens` | mint token | `{label, role_cap?, max_uses?, expires_at?}` | `201 {url, qr_payload, token_preview}` — raw token shown ONCE |
| `POST /guest-tokens/{id}/revoke` | revoke instantly | — | `200 {revoked_at}` |
| `GET /spaces/{id}/members` | list memberships | — | `200 [{membership, user}]` |
| `PATCH /spaces/{id}/members/{uid}` | change role | `{role}` | `200 {membership}` |
| `DELETE /spaces/{id}/members/{uid}` | remove / leave | — | `204` |
| `POST /spaces/{id}/invitations` | invite by email | `{email, role}` | `202 {invitation}` (email queued) |
| `GET /invitations/{token}` | invitation preview | token | `200 {space_title, role, inviter}` |
| `POST /invitations/{token}/accept` | accept (logged-in) | session | `200 {membership}` |
| `POST /invitations/{id}/revoke` | revoke pending invite | — | `200` |

Rules: token `role_cap=contributor` still gated by the space's
`contribution_policy`; revocation is immediate and invalidates in-flight
presigned URLs at confirm time; one pending invite per email per space (409).

## 9. Contributions (`/spaces/{id}/contributions`)

Actor: session user or guest token with contributor cap (subject to
`contribution_policy`; see PERMISSIONS_MATRIX).

| Method + path | Purpose | Request | Response |
|---|---|---|---|
| `POST /spaces/{id}/contributions` | create | `{kind, body?, guest_name?, is_anonymous?, is_private_to_owner?, taken_at?, asset_ids?, idempotency_key?}` + `Idempotency-Key` header | `201 {contribution}` or `202 {contribution: pending}` under pre-moderation |
| `GET /spaces/{id}/contributions` | list (gallery/timeline source) | `?kind=&q=&taken_from=&taken_to=&author=&sort=-taken_at&cursor=` | cursor list; private/pending filtered per actor |
| `GET /contributions/{cid}` | detail | — | `200 {contribution, attachments, reactions_summary, replies_preview}` |
| `PATCH /contributions/{cid}` | edit own (body/taken_at, 15-min window for guests) | `{body?, taken_at?}` | `200 {contribution}` |
| `DELETE /contributions/{cid}` | delete own (author) or any (moderator) | — | `204` |
| `POST /contributions/{cid}/reactions` | react | `{emoji}` (allowlisted) | `201 {reaction}` / `204` if already present |
| `DELETE /contributions/{cid}/reactions/{emoji}` | unreact | — | `204` |
| `GET /contributions/{cid}/replies` | list replies | cursor | list |
| `POST /contributions/{cid}/replies` | reply | `{body, guest_name?}` | `201 {reply}` |
| `DELETE /replies/{rid}` | delete own reply / moderate | — | `204` |

Validation: `body` required for message/story/private_note/future_letter
(1–20000 chars), forbidden as sole content for media/audio without assets;
`guest_name` 1–80, required for guests when the token has no prior name on
file; `is_anonymous=true` rejected when `allow_anonymous=false` (403);
`future_letter` requires `taken_at` (delivery date) in the future and creates
a `scheduled_events` row on accept.
Feeds: `GET …/contributions?sort=-taken_at` powers the timeline;
`?kind=media,audio` + asset renditions powers the gallery/slideshow;
`?sort=-created_at&limit=10` polled powers the live wall.

## 10. Media (`/media`)

Bytes flow browser↔storage; the API mints URLs and records metadata.

| Method + path | Purpose | Request | Response |
|---|---|---|---|
| `POST /media/presign` | reserve + mint upload URL | `{space_id, mime, bytes, kind?, contribution_id?}` | `201 {asset_id, upload_url, upload_expires_at, max_bytes, multipart?: {…}}` (multipart instructions when bytes > 100 MB) |
| `POST /media/confirm` | register bytes + start processing | `{asset_id}` + `Idempotency-Key` | `202 {asset, processing_job_id}` |
| `GET /media/{asset_id}` | metadata + signed view URLs | — | `200 {asset, urls: {original?, derivatives…}}` (original URL only for staff/owner per policy) |
| `GET /media/{asset_id}/download` | fresh signed download | `?derivative=` | `302` to signed URL (short TTL) |
| `DELETE /media/{asset_id}` | delete own / moderate | — | `204` (bytes purged async) |
| `GET /media/jobs/{job_id}` | processing status (poll) | — | `200 {status, attempts, asset?}` |

Validation: MIME allowlist (`image/jpeg|png|webp|heic`, `video/mp4|quicktime|
webm`, `audio/mpeg|mp4|wav|ogg|webm`, `application/pdf` for books);
per-file caps (image 25 MB, video 2 GB via multipart, audio 200 MB);
quota checked at presign AND confirm (`quota_exceeded` with numbers).
Confirm verifies the object exists and its size/sha256 match the reservation
(mismatch → `409`, reservation released).

## 11. AI Memory Studio (`/spaces/{id}/ai`)

Actor: owner/collaborator only; requires space `ai_opt_in=true`.

| Method + path | Purpose | Request | Response |
|---|---|---|---|
| `POST /spaces/{id}/ai/jobs` | enqueue generation | `{kind, inputs: {contribution_ids?/asset_ids?, options?}, idempotency_key?}` + `Idempotency-Key` | `202 {job_id, quota_reserved}` |
| `GET /spaces/{id}/ai/jobs` | list jobs | `?kind=&status=&cursor=` | list |
| `GET /ai/jobs/{job_id}` | status (poll) | — | `200 {job, outputs_preview?}` |
| `POST /ai/jobs/{job_id}/cancel` | cancel queued/running | — | `200 {job}` (quota refunded) |
| `GET /spaces/{id}/ai/assets` | list outputs | `?kind=&promoted_only=` | list (all carry `is_ai_labeled: true`) |
| `POST /ai/assets/{aid}/promote` | accept into gallery/timeline | — | `200 {asset}` |
| `DELETE /ai/assets/{aid}` | discard output | — | `204` |
| `GET /spaces/{id}/ai/quota` | budget view | — | `200 {plan_credits, used, reserved, resets_at}` |

Kind-specific `inputs`: transcription `{asset_ids (audio/video)}`;
categorization `{contribution_ids? (default: uncategorized)}`;
captions `{asset_ids}`; summary `{contribution_ids?/window?}`;
letter `{tone, from, to, contribution_ids?}`; book `{title, sections?, asset_ids?}`;
highlight_film `{asset_ids, max_duration_s?, aspect?}`.
Failures refund reserved quota automatically; `quota_exceeded` names the
kind + reset time. Provider errors surface as `upstream_error, retryable: true`.

## 12. Scheduling (`/spaces/{id}/schedule`, `/me/reminders`)

| Method + path | Purpose | Request | Response |
|---|---|---|---|
| `GET /spaces/{id}/schedule` | list events (staff) | `?kind=&status=&cursor=` | list of scheduled_events |
| `POST /spaces/{id}/schedule` | create event | `{kind: reveal/reminder/future_letter/capsule, run_at, timezone?, payload?}` + `Idempotency-Key` | `201 {event}` |
| `POST /schedule/{eid}/reschedule` | move (cancel + new version) | `{run_at}` | `200 {event (new version)}` |
| `POST /schedule/{eid}/cancel` | cancel | — | `200 {event}` |
| `GET /me/reminders` | my upcoming reminders/digests | `?from=&to=` | list across owned/followed spaces |
| `PATCH /me/reminder-prefs` | digest/reminder toggles | `{digest_enabled?, reminder_enabled?}` | `200 {prefs}` |

Validation: `run_at` must be future (≥ 5 min out); `timezone` must be IANA;
`future_letter` payload must reference an existing `future_letter`
contribution in the space; reveal events only one active per space (409).
Claimed/running events cannot be rescheduled (409, cancel after finish).

## 13. Moderation (`/spaces/{id}/moderation`)

Actor: owner/collaborator (+ admin).

| Method + path | Purpose | Request | Response |
|---|---|---|---|
| `GET /spaces/{id}/moderation/queue` | pending items (pre-mod + reports) | `?cursor=` | list of contributions/replies with `status=pending` or report counts |
| `POST /moderation/{target_type}/{target_id}/approve` | approve | — | `200 {target}` |
| `POST /moderation/{target_type}/{target_id}/hide` | hide from members | `{reason?}` | `200 {target}` + moderation_record |
| `POST /moderation/{target_type}/{target_id}/reject` | reject (pre-mod) | `{reason?}` | `200 {target}`; author notified with reason |
| `POST /moderation/{target_type}/{target_id}/restore` | restore hidden | — | `200 {target}` |
| `GET /spaces/{id}/moderation/log` | audit trail | cursor | list of moderation_records |
| `POST /contributions/{cid}/report` | member/guest report | `{reason}` | `202` (threshold may auto-hide per space rule) |

Every action writes a `moderation_records` row; authors see their own
rejected items with reasons; members never see hidden items (404 as invisible).

## 14. Archives, export, deletion (`/spaces/{id}/archives`, `/me/export`)

| Method + path | Purpose | Request | Response |
|---|---|---|---|
| `POST /spaces/{id}/archives` | enqueue export | `{kind: full_zip/book_pdf/film_mp4/data_export, options?}` + `Idempotency-Key` | `202 {archive_id}` (plan-gated: book/film premium) |
| `GET /spaces/{id}/archives` | list exports | cursor | list with `download_url?` when ready (TTL) |
| `GET /archives/{aid}/download` | fresh signed download | — | `302` to signed URL (owner/collaborator; expiry enforced, 410 after) |
| `GET /me/export` | personal data export (all my spaces/content) | — | `202 {archive_id}` (space_id NULL variant) |
| `POST /me/delete` | close account (soft) | `{confirm_email}` must match | `202` (sessions revoked; owned spaces must transfer/purge first or 409 lists them) |

Retention: export files expire after 7 days (status → `expired`, bytes
deleted); `data_export` is a machine-readable ZIP (JSON + originals manifest).

## 15. Billing (`/billing`, webhooks)

| Method + path | Purpose | Request | Response |
|---|---|---|---|
| `GET /billing/plans` | public plan table | — | `200 [{plan, prices, quotas, features}]` |
| `GET /billing/subscription` | my subscription + usage | session | `200 {subscription, usage: {storage, ai_credits}}` |
| `POST /billing/checkout` | start subscription/purchase | `{plan?/one_time?: {space_id, sku}, provider: paystack/stripe, success_url, cancel_url}` | `200 {checkout_url, ref}` |
| `POST /billing/cancel` | cancel at period end | — | `200 {subscription}` |
| `GET /billing/payments` | my receipts | cursor | list of payments (amounts, refs, no provider secrets) |
| `POST /webhooks/paystack` | provider events | provider-signed body | `200` (always 200 after signature verify; failures retried by provider) |
| `POST /webhooks/stripe` | provider events | provider-signed body | `200` (same) |

Webhook handling: verify signature → `UNIQUE(provider, provider_event_id)`
insert → apply (activate/renew/fail/refund) → queue receipt email.
Bad signature → `401` (provider retries, then alerts). Entitlement checks on
every gated endpoint read `subscriptions` + `usage_records`, never client claims.

## 16. Admin (`/admin`)

Actor: `role_global=admin` only. Read-mostly + support actions.

| Method + path | Purpose |
|---|---|
| `GET /admin/spaces?q=&cursor=` | find spaces (support) |
| `GET /admin/users?q=&cursor=` | find users |
| `GET /admin/jobs/dead` | dead-letter queues across media/AI/notify/export |
| `POST /admin/jobs/{queue}/{id}/retry` | manual retry |
| `GET /admin/usage` | platform usage rollups (no PII beyond support need) |
| `POST /admin/spaces/{id}/moderate` | hide/restore any content (writes moderation_record, rule=`admin`) |

Admin reads bypass space visibility but every access is audit-logged
(`moderation_records` for content actions; structured logs for reads).

## 17. OpenAPI and conformance

- The implementation MUST serve `GET /v1/openapi.json` generated from the
  route schemas; this document is the human contract, OpenAPI the machine one.
  CI fails if they drift (snapshot test).
- Contract tests: every endpoint above gets at least a happy-path + its
  named error cases (Pytest); guest flows get full journey tests (Playwright).
- Flow diagrams for auth, spaces, guest contribution, media, AI, and reveals:
  [DATA_FLOW.md](DATA_FLOW.md).

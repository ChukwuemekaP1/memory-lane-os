# Memory Lane — Privacy, Retention & Deletion

How personal data is stored, how long it is kept, and how it is removed.
User-facing summary of the enforced rules; the normative behavior lives in
the API and the purge jobs.

## 1. What lives where

| Data | Store | Notes |
|---|---|---|
| Accounts, spaces, contributions | PostgreSQL | system of record |
| Original uploads | Object storage `originals/` | immutable, never modified |
| Previews/thumbnails/transcodes | Object storage `derivatives/` | regenerated any time |
| Exports (ZIP/PDF/film) | Object storage `exports/` | expire after 7 days |
| Queues, OTP codes, rate limits | Redis (+ memory fallback) | TTL-bound, disposable |
| AI outputs | PostgreSQL + object storage | labeled AI-assisted, deletable |

## 2. Retention rules

- **Memories:** kept until the owner deletes them. Soft-deleted spaces are
  recoverable for 30 days, then eligible for purge.
- **Exports:** download links expire after 7 days; files are deleted.
- **Sessions:** expire after 30 days; logout revokes immediately.
- **OTP/magic challenges:** expire after 10 minutes; audit rows are swept hourly.
- **Notifications:** sent-mail history is trimmed to stubs after 180 days.
- **Finished schedule events:** retained 90 days as an audit trail.
- **Financial records (payments, metering, live subscriptions):** retained as
  accounting evidence even after account purge (pseudonymous afterwards).
- **AI provider side:** prompts are minimized (transcripts/derivatives over
  originals); provider retention follows the configured provider's policy and
  is disclosed in product copy before launch.

## 3. Deletion workflows

### 3.1 Delete a contribution or reply

Author or space staff. Soft delete (hidden immediately, recoverable by
support for 30 days). Attached bytes stay until the asset itself is deleted.

### 3.2 Delete a space (owner)

`DELETE /v1/spaces/{id}` soft-deletes (recoverable 30 days via restore).
`POST /v1/spaces/{id}/purge` (title confirmation) permanently removes the
space, its content, and its bytes via a background job. Purge is final.

### 3.3 Close vs purge an account

- **Close** (`POST /v1/me/delete`): requires owned spaces to be transferred
  or deleted first; revokes all sessions immediately; content the user
  authored stays attributed until purge.
- **Purge** (`POST /v1/me/purge`): irreversible. Email/display name are
  scrubbed, sessions/OTP rows removed, authored content tombstoned to
  "Deleted member", memberships removed, scheduled personal events
  cancelled. Financial rows keep amounts against the pseudonymous id.

### 3.4 Export your data

- Space owners: full ZIP / data export per space (originals included).
- Anyone: `GET /v1/me/export` builds a personal archive of owned spaces.
- Exports are async, expire in 7 days, and need owner/staff rights (or a
  single-purpose share link the owner mints).

## 4. Privacy guarantees

- Private-to-owner messages are visible only to the owner (and admins for
  support) — never in feeds, exports for others, digests, or AI inputs.
- Pending/rejected contributions are visible only to staff and their author.
- AI processing requires per-space opt-in and excludes private, pending,
  hidden, and rejected content — always.
- Guest tokens are revocable, expirable, and use-capped; revocation is instant.
- Every privileged access (admin support reads, moderation actions) is logged.

# Memory Lane — Permissions Matrix

Date: 2026-11-17
Stage: Stage 1 — Discovery and System Design, Prompt 04
Design only — no code exists or was changed.

Authoritative allow/deny table for every endpoint in
[API_SPECIFICATION.md](API_SPECIFICATION.md), enforced server-side by the
`permissions` module (ADR-006). UI hiding is cosmetic; the API re-checks
every request.

Legend: ✅ allowed · ❌ denied (403, or 404 where invisibility applies) ·
◐ conditional (note number) · — not applicable.

## 1. Actors

| Actor | How the API recognizes them |
|---|---|
| Owner | session user = `spaces.owner_id` |
| Collaborator | session user with membership `role=collaborator` |
| Contributor (member) | session user with membership `role=contributor` |
| Contributor (guest) | valid guest token, `role_cap=contributor` (+ optional name) |
| Anonymous guest | contributor guest with `is_anonymous` on the item (actor class, not a credential) |
| Viewer (member) | session user with membership `role=viewer` |
| Viewer (guest) | valid guest token, `role_cap=viewer` |
| Stranger | no credential, or credential for another space |
| Admin | session user with `role_global=admin` (support powers, audit-logged) |

Actor resolution order per request: session cookie → guest bearer/query token.
If both are present and disagree, the session wins and the token is ignored
(logged once per request id for abuse forensics, token never logged).

Token validity (all must hold): exists · not revoked · not expired ·
`use_count < max_uses` (when set) · space not deleted · space visible to
link-holders (`link`, `public`, or `scheduled` + published; never `private`).

## 1b. Visibility semantics (read vs write)

| Visibility | Reads | Writes |
|---|---|---|
| `public` | anyone, no credential needed | credential + policy (as below) |
| `link` (unlisted) | members, staff, valid token holders | contributor credential + policy |
| `private` | members and staff only; tokens grant nothing | members only (+ staff) |
| `scheduled` (unpublished) | staff preview only | staff only |
| `scheduled` (published) | as `link` | as `link` |
| soft-deleted | owner only (for restore) | none (restore first) |

There is no public discovery feed: `public` spaces are still reached via
their link/QR, but the link works for strangers (reads need no token).

## 2. Space-level matrix

| Capability | Owner | Collab | Contrib (m/g) | Viewer (m/g) | Stranger | Admin |
|---|---|---|---|---|---|---|
| View space home + theme | ✅ | ✅ | ✅ | ✅ | ◐1 | ✅ |
| Edit title/desc/dates/location | ✅ | ◐2 | ❌ | ❌ | ❌ | ❌ |
| Change theme (entitled) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Change privacy/policy/moderation | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Publish / schedule reveal | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Mint / revoke guest tokens | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Invite / manage members | ✅ | ◐3 | ❌ | ❌ | ❌ | ❌ |
| Edit space settings (reminders) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Soft-delete / restore space | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Purge space | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Transfer ownership | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

1. Strangers see `visibility=link` spaces only with a valid token — without a
   token they are 404. `private` spaces are 404 to everyone except staff,
   members, and valid token holders. `scheduled` spaces are 404 until
   `publish_at` passes (owner/collaborator see a preview banner).
2. Collaborators may edit title/description/dates/location/cover only —
   never privacy, policy, tokens, or deletion.
3. Collaborators may invite contributors/viewers, never collaborators;
   may revoke invites they created.

## 3. Contribution matrix

Effective write access = token/member role ∩ space `contribution_policy`:

| Policy | Who may post |
|---|---|
| `owner_only` | owner (+ collaborator) |
| `members` | owner, collaborator, member contributors |
| `link_contributors` | above + guest contributor tokens |
| `anyone_with_link` | above + guest viewer tokens may also post (upgrade-to-post) |

| Capability | Owner | Collab | Contrib | Viewer | Stranger | Admin |
|---|---|---|---|---|---|---|
| Post (per policy above) | ✅ | ✅ | ◐4 | ◐4 | ❌ | ❌ |
| Post anonymous (`is_anonymous`) | ✅ | ✅ | ◐5 | ◐5 | ❌ | — |
| Post private-to-owner | ✅ | ✅ | ✅ | ❌ | ❌ | — |
| View visible items | ✅ | ✅ | ✅ | ✅ | ◐1 | ✅ |
| View pending (pre-mod) | ✅ | ✅ | own only | ❌ | ❌ | ✅ |
| View hidden/rejected | ✅ | ✅ | own+reason | ❌ | ❌ | ✅ |
| View private-to-owner | ✅ | ❌ | own only | ❌ | ❌ | ✅ |
| Edit own (window) | ✅ | ✅ | ◐6 | — | — | ❌ |
| Delete own | ✅ | ✅ | ✅ | — | — | ❌ |
| Moderate any (approve/hide/reject/restore) | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ |
| Report item | ✅ | ✅ | ✅ | ✅ | ❌ | — |

4. Posting requires BOTH a contributor-capable credential AND the policy to
   allow that actor class. Guests additionally need the token valid at
   confirm time (Section 6, note 12).
5. Anonymous posting requires `allow_anonymous=true`, else 403. Anonymous
   items hide the name from everyone except owner/admin (who see the token
   label for moderation).
6. Edit window: members 24 h, guests 15 min, owner/collaborator anytime for
   own items; mods never edit others' items (hide + ask instead).

## 4. Media matrix

| Capability | Owner | Collab | Contrib | Viewer | Stranger | Admin |
|---|---|---|---|---|---|---|
| Presign upload (per post policy) | ✅ | ✅ | ◐4 | ◐4 | ❌ | ❌ |
| Confirm upload | ◐7 | ◐7 | ◐7 | ◐7 | ❌ | ❌ |
| View derivatives (gallery/wall) | ✅ | ✅ | ✅ | ✅ | ◐1 | ✅ |
| View/download original | ✅ | ✅ | own only | ❌ | ❌ | ✅ |
| Delete asset | ✅ | ✅ | own only | ❌ | ❌ | ✅ |

7. Confirm requires: reservation owned by the same actor (user id or token
   id match) + token still valid + quota still available. Mismatch → 409/410.

## 5. Interactions matrix

| Capability | Owner | Collab | Contrib | Viewer | Stranger | Admin |
|---|---|---|---|---|---|---|
| React to visible items | ✅ | ✅ | ✅ | ◐8 | ❌ | ❌ |
| Reply to visible items | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| Delete own reaction/reply | ✅ | ✅ | ✅ | ✅ | — | ❌ |
| Hide any reply (moderate) | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ |

8. Guest viewers react only when `allow_viewer_react=true`; member viewers
   may always react. Nobody reacts to pending/hidden items except staff.
8b. Replies follow posting rights (`can_post`): anyone who may post in the
   space may reply. Under `anyone_with_link` this includes viewer-cap
   token holders; the Viewer-column ❌ in Section 5 applies to spaces that
   did not open posting to them.

## 6. AI Studio, scheduling, exports, billing

| Capability | Owner | Collab | Contrib | Viewer | Stranger | Admin |
|---|---|---|---|---|---|---|
| AI enqueue / cancel / promote | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| AI view jobs + outputs | ✅ | ✅ | ❌ | ❌ | ❌ | ◐9 |
| AI view quota | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Schedule reveal/reminder/capsule | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Create future_letter contribution | ✅ | ✅ | ✅ | ❌ | ❌ | — |
| View schedule list | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ |
| Enqueue/list/download exports | ✅ | ◐10 | ❌ | ❌ | ❌ | ❌ |
| Per-item download (own + visible) | ✅ | ✅ | ✅ | ◐11 | ❌ | ✅ |
| Manage subscription/payments | own | own | own | own | — | ❌ |

9. Admins see job metadata (counts, errors) for support, never prompt/output
   content — AI content is private memory.
10. Collaborators may enqueue/list/download `full_zip` and `data_export`
    (space scope) but not `book_pdf`/`film_mp4` (premium owner-gated) and
    never `purge`.
11. Viewers download derivatives of visible items only, never originals.

## 7. Edge cases (normative)

12. **Token revoked mid-upload:** presigned URL still works (storage can't
    know), but `confirm` fails `410` and the orphaned bytes are janitor-
    swept after 24 h. The client must surface "link revoked — ask for a
    new link" with retry.
13. **Token expires between list and post:** the POST fails `410`; lists
    already rendered stay visible until refresh (no retroactive hiding).
14. **Policy tightened after posting:** existing items keep their visibility;
    new posts follow the new policy. No silent unpublishing.
15. **Member removed:** their items stay (attributed); their pending invites
    die; their sessions lose space access immediately (membership checked
    per request, never cached beyond 60 s).
16. **Pre-moderation enabled later:** already-visible items stay visible;
    only new posts enter the queue.
17. **Space moved private → link:** tokens minted while private become
    usable (validity re-evaluated per request); the reverse move
    (`link → private`) disables all token access instantly while keeping
    member access.
18. **Scheduled space publishes:** `publish_at` passing flips visibility via
    the reveal event; until the event runs `done`, viewers still get 404
    (no half-published state). Owner preview never leaks to others.
19. **Anonymous + private combo:** allowed — owner sees "anonymous + token
    label", everyone else sees nothing (private wins).
20. **Admin invisibility rule:** admin access never appears in member-visible
    logs (no "admin viewed" noise) but is fully audit-logged server-side.
21. **Billing past-due:** read/react/download continue; presign, AI enqueue,
    premium themes, and new exports block with `quota_exceeded` after the
    grace window. Downgrade never deletes anything.
22. **Purge in flight:** the space 404s for everyone (including owner) once
    the purge job starts; the owner gets completion email + receipt.

## 8. Enforcement checklist (for implementation)

- [ ] Every route declares `require = <capability>`; no route is open by default.
- [ ] Actor resolution (session vs token) in one middleware; runs before routing.
- [ ] Membership + token validity re-checked per request (≤ 60 s cache).
- [ ] `not_found` for invisible, `forbidden` for visible-but-denied, `gone`
      for revoked/expired — per API_SPECIFICATION Section 2.
- [ ] Private/pending/hidden filtering in the query layer, not the serializer.
- [ ] Original-byte URLs minted only per Section 4; derivatives per visibility.
- [ ] Pytest: each matrix cell above has at least one allow + one deny test;
      Section 7 edge cases each have a dedicated test.
- [ ] Playwright: guest post → revoke → confirm-fails journey; pre-mod
      approve journey; scheduled reveal journey.

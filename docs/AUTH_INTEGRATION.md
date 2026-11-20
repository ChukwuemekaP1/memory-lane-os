# Memory Lane — Auth Integration (Neon Managed Better Auth)

Status: **Live-integrated and end-to-end verified on `dev`** (`2026-11-19`).

## 1. Architecture (Single Active Session Model)

When `NEON_AUTH_ENABLED=true` (backend) and `NEXT_PUBLIC_AUTH_PROVIDER=neon` (frontend), Neon Managed Better Auth is the **sole** user authentication provider. Conflicting custom cookie/OTP sessions are disabled (`_session_actor` ignores custom cookies; `/v1/auth/request-code`, `/verify`, `/magic`, `/refresh` return `409 Conflict`). Guest space tokens remain supported for unauthenticated guest contributions without accounts.

## 2. Frontend (`@neondatabase/auth` + Next.js 16 App Router)

- **SDK:** `@neondatabase/auth` `0.6.0-beta`
- **Server instance:** `frontend/lib/neon-auth-server.ts` (`createNeonAuth` with `NEON_AUTH_BASE_URL` and 32+ char `NEON_AUTH_COOKIE_SECRET`)
- **Catch-all handler:** `frontend/app/api/auth/[...path]/route.ts` (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`)
- **Protected route proxy:** `frontend/proxy.ts` protecting `/dashboard/:path*`, `/s/:spaceId/settings/:path*`, and `/s/:spaceId/studio/:path*` (redirects unauthenticated users to `/login`)
- **Client & bearer token injection:** `frontend/lib/neon-auth-client.ts`, `frontend/lib/auth-provider.ts` (`getAuthToken()` fetches and caches the short-lived JWT from `/api/auth/token`, cleared on `signOutCurrentUser()`), and `frontend/lib/api.ts` (automatically attaches `Authorization: Bearer <jwt>` unless an explicit guest token is passed)
- **UI flows:** `frontend/app/login/page.tsx` (sign-in, registration, account recovery/password reset + `/v1/auth/me` sync) and `frontend/app/dashboard/page.tsx` (sign-out)

## 3. Backend (`FastAPI` JWKS Verification & Profile Sync)

- **Verifier:** `backend/app/modules/identity/neon.py` (`NeonAuthVerifier`)
  - Fetches & caches public keys from `NEON_AUTH_JWKS_URL` (TTL `NEON_AUTH_JWKS_TTL_SECONDS`).
  - Verifies asymmetric signatures (`EdDSA` / `Ed25519` used by Neon Auth, plus `RS256` and `ES256`; explicitly rejects `HS256`/`none`), `iss`, `aud`, `exp`, and `sub`.
  - Reads both `emailVerified` and `email_verified`.
- **Profile synchronization:** `backend/app/modules/permissions/actor.py` maps verified `sub` to `users.neon_auth_sub`, provisions local `User` rows on first verified request, syncs `display_name` and `email_verified_at`, and never trusts request-supplied user IDs.

## 4. Live Verification Summary (`dev`)

- Real registration (`200`), JWT issuance (`EdDSA`), FastAPI JWKS verification & profile sync (`200`)
- Unauthorized access (`401`), forged JWT (`401`), conflicting custom auth blocked (`409`)
- Logout, logged-out token denial, re-login, and session restoration to the exact same `user_id`
- Frontend Vitest (`auth-provider.test.ts`, 16/16 total tests) + `tsc --noEmit` + `next build` passed

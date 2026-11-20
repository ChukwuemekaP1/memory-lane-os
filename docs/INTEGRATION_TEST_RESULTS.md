# Memory Lane — Live Integration Test Results

Executed: **2026-11-19** against live Neon `dev` branch (`br-damp-truth-beh9ifs1`), live Neon Managed Better Auth (`ep-shiny-fog-be5iot59`), live Neon Object Storage private bucket `assets` (`br-damp-truth-beh9ifs1`), and live OpenRouter (`https://openrouter.ai/api/v1`). Zero fake providers or mock responses used.

## 1. Phase 10 End-to-End Suite (9 / 9 Passed)

| Test | Journey | Observed Live Result | Status |
|---|---|---|---|
| **Test 1** | Authentication | Registered real Neon Auth user, issued `EdDSA` JWT, verified against live JWKS on FastAPI (`user_id=01a1f1ad-310a-7e8b-b4a8-93b1dd3c9e92`), logged out, verified token revoked, re-logged in, verified same `user_id`; unauthorized (`401`), forged JWT (`401`), conflicting custom OTP (`409`) rejected | **PASS** |
| **Test 2** | Memory creation | Created space `01a1f1ad-6775-7733-bef9-17c7c656dcd4` (`Ada 30th Live E2E`), enabled `ai_opt_in=true`, verified persisted in Neon `dev` PostgreSQL and returned by owner dashboard (`GET /v1/spaces`) | **PASS** |
| **Test 3** | Guest contribution | Minted contributor guest token, posted identified + anonymous guest messages without registering, verified visible in owner feed, added owner reaction (`🎉`) and reply | **PASS** |
| **Test 4** | Media upload | Uploaded real PNG (`24,756 B`, via guest), MP4 (`21,707 B`), and WAV (`32,044 B`) via presigned PUT → confirmed → FFmpeg processed (`renditions=2` image, `2` video, `1` audio); signed GET matched exact bytes; unauthenticated direct S3 GET returned `403`; real deletion verified `204` + `404` + removed from S3 | **PASS** |
| **Test 5** | AI Memory Studio | Ran real OpenRouter `captions` (`$0.000154`), `transcription` (`$0.000015`), `categorization` (`$0.000194`), `summary` (`$0.000308`); verified idempotency key returns same `job_id`; verified `is_private_to_owner=true` secret note was excluded from AI summary | **PASS** |
| **Test 6** | Keepsake generation | Ran real OpenRouter `letter` (`$0.001138`), edited title (`PATCH`), approved/promoted (`POST /promote`), ran `book` (`$0.000516`), verified `book_pdf` premium entitlement gate (`403` on free plan), built real `full_zip` archive stored in Neon Object Storage (`exports/...`) + email notification | **PASS** |
| **Test 7** | Highlight video | Ran real `highlight_film` on uploaded PNG + MP4: AI clip selection (`$0.000230`) + FFmpeg MP4 render (`23,844 B`) stored in Neon Object Storage (`generated/...`) and downloaded via signed URL | **PASS** |
| **Test 8** | Permissions | Registered second real Neon Auth user B; switched space to `private`; verified User B rejected with `404` on space, media metadata, media download, AI jobs, and archives | **PASS** |
| **Test 9** | Application consistency | Signed out User A and signed back in with fresh JWT; verified space + 7 AI jobs + 7 AI assets + 1 archive all persisted and retrievable | **PASS** |

## 2. Additional Verification Runs

- **Image generation (live OpenRouter `google/gemini-3.1-flash-image`):** Succeeded (`in=14`, `out=1120`, `cost=$0.067207`), generated image stored in Neon Object Storage (`generated/...`) and registered in PostgreSQL `media_assets` + `ai_generated_assets`.
- **Database preflight (`neon_db_preflight.py`):** `EXIT_CODE: 0`, `alembic_version: 0007`, 27 tables (26 app + `alembic_version`), 30 enums, **`MATCH`**.
- **Frontend verification:** `tsc --noEmit` (0 errors), `vitest run` (6/6 files, 16/16 tests passed), `next build` (exit code 0).

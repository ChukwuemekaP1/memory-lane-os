# Memory Lane — OpenRouter Production Integration

Status: **Connected and live-verified against `https://openrouter.ai/api/v1`** (`2026-11-19`).

## 1. Security & Configuration

- **Base URL:** `https://openrouter.ai/api/v1` (`OPENROUTER_BASE_URL`)
- **API Key:** Server-side only (`OPENROUTER_API_KEY` in `.env`); never exposed in frontend code, client bundles, logs, or error responses.
- **No silent fake fallback:** `AI_PROVIDER=openrouter` raises explicit non-retryable configuration errors (`not_configured` / `unsupported`) if a required model or key is missing. `FakeProvider` is strictly opt-in for offline unit tests.
- **Cost & usage tracking:** `OpenRouterProvider` (`backend/app/services/ai/providers.py`) records `model`, `input_tokens`, `output_tokens`, and actual provider USD cost (`usage.cost`) on every `AIGenerationJob` row and logs only token/cost telemetry.

## 2. Live-Verified Model Capability Matrix

Catalog discovery against `GET /api/v1/models` (445 live models) identified two non-existent model IDs in the initial `.env` (`openai/whisper-large-v3` and `google/gemini-3.1-flash-video`), which were replaced with live-verified models:

| Capability | Env Var | Verified Model ID | Verified Modalities / Features | Observed Live Cost (Test Run) |
|---|---|---|---|---|
| Text (summary, categorization, letter, book, story enhancement, highlight selection) | `OPENROUTER_TEXT_MODEL` | `deepseek/deepseek-v4.1-flash` | `in: [text, image]`, `out: [text]`, `response_format`, `structured_outputs` | \$0.00019 – \$0.00114 / job |
| Vision (captions, image analysis) | `OPENROUTER_VISION_MODEL` | `deepseek/deepseek-v4.1-flash` | `in: [text, image]`, JSON mode; grounded prompt forbids inventing details | \$0.00015 – \$0.00018 / image |
| Audio transcription | `OPENROUTER_TRANSCRIPTION_MODEL` + `AI_AUDIO_SUPPORTED=true` | `google/gemini-2.5-flash-lite` | `in: [text, image, file, audio, video]`, `out: [text]`; normalized audio format (`wav`, `mp3`, `ogg`, `m4a`, `webm`) | \$0.000015 / clip |
| Image generation | `OPENROUTER_IMAGE_MODEL` | `google/gemini-3.1-flash-image` | `in: [image, text]`, `out: [image, text]`, `modalities: ["image", "text"]` | \$0.067207 / image |
| Video generation / Highlight film | `OPENROUTER_VIDEO_MODEL` + FFmpeg | `google/gemini-omni-1.2-flash` (catalog-verified) + FFmpeg assembly | Highlight films use AI clip selection (`deepseek/deepseek-v4.1-flash`) + real FFmpeg MP4 assembly stored in Neon Object Storage | \$0.000230 AI selection + local FFmpeg render |

## 3. Cost-Sensitive Operations

- **Low cost (< \$0.002/job):** Summary, categorization, captions, audio transcription, letters, book chapters, highlight selection.
- **Moderate cost (~\$0.07/image):** `image_generation` (`google/gemini-3.1-flash-image` — \$0.0672 observed for one image).
- **High cost (deferred until explicitly budgeted):** Direct generative video synthesis (`google/gemini-omni-1.2-flash`). Highlight films currently use low-cost AI selection + deterministic FFmpeg rendering from real uploaded user media.
- **Guardrails:** `OPENROUTER_MAX_JOB_COST_USD=0.50`, monthly plan token budgets (`free=100,000`, `premium=5,000,000`), and per-job idempotency keys.

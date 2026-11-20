"""AI providers: OpenRouter (OpenAI-compatible) + deterministic fake.

All calls return AIResult (text + usage). Failures raise AIError with a
retryable flag the studio executor uses for backoff vs dead decisions.
Only token counts are logged — never prompts, media, or keys.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.config import Settings
from app.logging import get_logger

logger = get_logger(__name__)


class AIError(Exception):
    def __init__(self, message: str, *, retryable: bool, code: str = "upstream_error") -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.code = code


@dataclass
class AIResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    cost_usd: float | None = None
    images: list[tuple[bytes, str]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class AIProvider(Protocol):
    name: str

    async def complete_text(self, system: str, user: str, *, json_mode: bool,
                            max_tokens: int) -> AIResult: ...
    async def complete_vision(self, system: str, user: str, images: list[bytes],
                              image_mimes: list[str], *, json_mode: bool,
                              max_tokens: int) -> AIResult: ...
    async def transcribe(self, audio: bytes, mime: str, *, language: str = "en") -> AIResult: ...
    async def generate_image(self, prompt: str, *, aspect_ratio: str | None = None) -> AIResult: ...


class OpenRouterProvider:
    """OpenAI-compatible chat API (default base: OpenRouter)."""

    name = "openrouter"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.openrouter_api_key:
            raise AIError("AI is not configured (missing OPENROUTER_API_KEY).",
                          retryable=False, code="not_configured")
        self._settings = settings
        self._client = client
        self._owns_client = client is None

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        close = False
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=self._settings.ai_timeout_seconds)
            close = True
        try:
            response = await client.post(
                f"{self._settings.openrouter_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._settings.openrouter_api_key}",
                    "HTTP-Referer": self._settings.frontend_base_url,
                    "X-Title": "Memory Lane",
                },
                json=payload,
            )
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise AIError(f"AI provider unreachable: {type(exc).__name__}.",
                          retryable=True) from exc
        finally:
            if close:
                await client.aclose()
        if response.status_code == 401:
            raise AIError("AI provider rejected credentials.", retryable=False, code="auth")
        if response.status_code == 429:
            raise AIError("AI provider rate-limited.", retryable=True, code="rate_limited")
        if response.status_code >= 500:
            raise AIError(f"AI provider error {response.status_code}.", retryable=True)
        if response.status_code >= 400:
            raise AIError(f"AI request refused ({response.status_code}).",
                          retryable=False, code="refused")
        try:
            return response.json()
        except ValueError:
            raise AIError("AI provider returned invalid JSON.", retryable=True) from None

    @staticmethod
    def _extract_images(message: dict[str, Any]) -> list[tuple[bytes, str]]:
        out: list[tuple[bytes, str]] = []
        candidates: list[Any] = []
        if isinstance(message.get("images"), list):
            candidates.extend(message["images"])
        if isinstance(message.get("content"), list):
            candidates.extend(message["content"])
        for item in candidates:
            if not isinstance(item, dict):
                continue
            url = None
            if isinstance(item.get("image_url"), dict):
                url = item["image_url"].get("url")
            elif isinstance(item.get("url"), str):
                url = item["url"]
            if isinstance(url, str) and url.startswith("data:") and ";base64," in url:
                header, b64 = url.split(";base64,", 1)
                mime = header[5:] or "image/png"
                try:
                    out.append((base64.b64decode(b64), mime))
                except ValueError:
                    continue
        return out

    @staticmethod
    def _extract(data: dict[str, Any], model: str) -> AIResult:
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise AIError("AI provider returned an unexpected shape.", retryable=True) from None
        content = message.get("content")
        if isinstance(content, list):
            text = "\n".join(
                part.get("text", "") for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ).strip()
        else:
            text = str(content or "")
        images = OpenRouterProvider._extract_images(message)
        usage = data.get("usage") or {}
        raw_cost = usage.get("cost")
        cost_usd = float(raw_cost) if isinstance(raw_cost, (int, float)) else None
        return AIResult(
            text=text,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            model=str(data.get("model") or model),
            cost_usd=cost_usd,
            images=images,
        )

    @staticmethod
    def _audio_format(mime: str) -> str:
        clean = mime.split(";")[0].strip().lower()
        mapping = {
            "audio/wav": "wav",
            "audio/x-wav": "wav",
            "audio/mpeg": "mp3",
            "audio/mp3": "mp3",
            "audio/mp4": "m4a",
            "audio/x-m4a": "m4a",
            "audio/ogg": "ogg",
            "audio/webm": "webm",
            "audio/flac": "flac",
            "audio/aac": "aac",
        }
        return mapping.get(clean, clean.split("/")[-1])

    async def complete_text(self, system: str, user: str, *, json_mode: bool,
                            max_tokens: int) -> AIResult:
        if not self._settings.ai_text_model:
            raise AIError("Text model is not configured (OPENROUTER_TEXT_MODEL / AI_TEXT_MODEL).",
                          retryable=False, code="not_configured")
        payload: dict[str, Any] = {
            "model": self._settings.ai_text_model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = await self._post(payload)
        result = self._extract(data, self._settings.ai_text_model)
        logger.info("ai text usage=%d cost=%s", result.total_tokens, result.cost_usd)
        return result

    async def complete_vision(self, system: str, user: str, images: list[bytes],
                              image_mimes: list[str], *, json_mode: bool,
                              max_tokens: int) -> AIResult:
        if not self._settings.ai_vision_model:
            raise AIError("Vision model is not configured (OPENROUTER_VISION_MODEL / AI_VISION_MODEL).",
                          retryable=False, code="not_configured")
        parts: list[dict[str, Any]] = [{"type": "text", "text": user}]
        for raw, mime in zip(images, image_mimes):
            encoded = base64.b64encode(raw).decode()
            parts.append({"type": "image_url",
                          "image_url": {"url": f"data:{mime};base64,{encoded}"}})
        payload: dict[str, Any] = {
            "model": self._settings.ai_vision_model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": parts}],
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = await self._post(payload)
        result = self._extract(data, self._settings.ai_vision_model)
        logger.info("ai vision usage=%d images=%d cost=%s",
                    result.total_tokens, len(images), result.cost_usd)
        return result

    async def transcribe(self, audio: bytes, mime: str, *, language: str = "en") -> AIResult:
        if not self._settings.ai_audio_supported:
            raise AIError("Transcription is not supported by the configured AI provider.",
                          retryable=False, code="unsupported")
        if not self._settings.ai_audio_model:
            raise AIError("Transcription model is not configured (OPENROUTER_TRANSCRIPTION_MODEL / AI_AUDIO_MODEL).",
                          retryable=False, code="not_configured")
        encoded = base64.b64encode(audio).decode()
        fmt = self._audio_format(mime)
        payload: dict[str, Any] = {
            "model": self._settings.ai_audio_model,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Transcribe this audio faithfully in language '{language}'. "
                            "Return only the verbatim transcript with no extra commentary. "
                            "If there is no speech, reply with '[No speech detected]'."
                        ),
                    },
                    {"type": "input_audio",
                     "input_audio": {"data": encoded, "format": fmt}},
                ],
            }],
        }
        data = await self._post(payload)
        result = self._extract(data, self._settings.ai_audio_model)
        logger.info("ai transcription usage=%d cost=%s", result.total_tokens, result.cost_usd)
        return result

    async def generate_image(self, prompt: str, *, aspect_ratio: str | None = None) -> AIResult:
        if not self._settings.ai_image_model:
            raise AIError("Image generation model is not configured (OPENROUTER_IMAGE_MODEL / AI_IMAGE_MODEL).",
                          retryable=False, code="not_configured")
        payload: dict[str, Any] = {
            "model": self._settings.ai_image_model,
            "modalities": ["image", "text"],
            "messages": [{"role": "user", "content": prompt}],
        }
        if aspect_ratio:
            payload["image_config"] = {"aspect_ratio": aspect_ratio}
        data = await self._post(payload)
        result = self._extract(data, self._settings.ai_image_model)
        if not result.images:
            raise AIError("Image generation model returned no image output.",
                          retryable=True, code="upstream_error")
        logger.info("ai image_gen usage=%d images=%d cost=%s",
                    result.total_tokens, len(result.images), result.cost_usd)
        return result


class FakeProvider:
    """Deterministic stub for tests and offline dev. No network, no cost."""

    name = "fake"

    def __init__(self, settings: Settings | None = None) -> None:
        self.calls: list[tuple[str, str]] = []

    async def complete_text(self, system: str, user: str, *, json_mode: bool,
                            max_tokens: int) -> AIResult:
        self.calls.append(("text", user[:80]))
        lowered = (system + "\n" + user).lower()
        if "categorize" in lowered:
            return AIResult(text=json.dumps({"categories": ["family", "celebration"]}),
                            input_tokens=50, output_tokens=10, model="fake")
        if "summar" in lowered:
            return AIResult(text="A joyful collection of shared memories.", input_tokens=80,
                            output_tokens=12, model="fake")
        if "letter" in lowered:
            return AIResult(text="Dear friend,\n\nWhat a wonderful day that was.\n\nWith love",
                            input_tokens=60, output_tokens=20, model="fake")
        if "book" in lowered or "manuscript" in lowered:
            return AIResult(
                text=json.dumps({"title": "Our Story",
                                 "sections": [{"title": "Beginnings", "text": "It started..."}]}),
                input_tokens=90, output_tokens=30, model="fake")
        if "highlight" in lowered:
            return AIResult(text=json.dumps({"clips": []}), input_tokens=40,
                            output_tokens=8, model="fake")
        return AIResult(text="Fake response.", input_tokens=20, output_tokens=5, model="fake")

    async def complete_vision(self, system: str, user: str, images: list[bytes],
                              image_mimes: list[str], *, json_mode: bool,
                              max_tokens: int) -> AIResult:
        self.calls.append(("vision", user[:80]))
        if json_mode:
            return AIResult(text=json.dumps({"captions": ["A lovely moment."] * max(1, len(images))}),
                            input_tokens=100, output_tokens=15, model="fake")
        return AIResult(text="A lovely moment.", input_tokens=100, output_tokens=10, model="fake")

    async def transcribe(self, audio: bytes, mime: str, *, language: str = "en") -> AIResult:
        self.calls.append(("transcribe", mime))
        return AIResult(text="[Fake transcript] Hello from the celebration!",
                        input_tokens=len(audio) // 1000 + 10, output_tokens=12, model="fake")

    async def generate_image(self, prompt: str, *, aspect_ratio: str | None = None) -> AIResult:
        self.calls.append(("generate_image", prompt[:80]))
        tiny_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        return AIResult(
            text="Generated image.",
            input_tokens=40,
            output_tokens=10,
            model="fake",
            cost_usd=0.0,
            images=[(tiny_png, "image/png")],
        )


_provider: AIProvider | None = None


def get_ai_provider(settings: Settings | None = None) -> AIProvider:
    global _provider
    if _provider is not None:
        return _provider
    if settings is None:
        from app.config import get_settings

        settings = get_settings()
    if settings.ai_provider == "fake":
        _provider = FakeProvider(settings)
    else:
        _provider = OpenRouterProvider(settings)
    return _provider


def set_ai_provider(provider: AIProvider) -> None:
    global _provider
    _provider = provider


def reset_ai_provider() -> None:
    global _provider
    _provider = None

"""Central configuration. All settings come from the environment (.env supported).

The app fails fast at startup when required secrets are missing or invalid.
See /.env.example for the full variable list.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "memorylane-api"
    app_version: str = "0.1.0"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False

    # Database: postgresql+asyncpg://user:pass@host:port/db
    # (postgresql+psycopg:// also accepted).
    database_url: str = Field(default="postgresql+asyncpg://memorylane:memorylane@127.0.0.1:5432/memorylane_dev")
    db_pool_size: int = 5
    db_pool_max_overflow: int = 5

    # Redis (queues, OTP hot path, rate limits). Empty = memory backends.
    redis_url: str = ""

    # Object storage. driver=filesystem for local dev/tests, s3 otherwise.
    storage_driver: Literal["filesystem", "s3"] = "filesystem"
    storage_dir: str = "./.devdata/storage"
    s3_endpoint_url: str = ""
    s3_bucket_originals: str = "memorylane-originals"
    s3_bucket_derivatives: str = "memorylane-derivatives"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "auto"
    # Neon Object Storage env names (auto-mapped into s3_* when s3_* are empty).
    aws_endpoint_url_s3: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = ""

    # Email. driver=file writes one JSON file per message (dev);
    # driver=memory keeps an in-process outbox (tests); smtp sends for real.
    mail_driver: Literal["memory", "file", "smtp"] = "file"
    mail_dir: str = "./.devdata/mail"
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False
    mail_from: str = "Memory Lane <hello@example.com>"
    frontend_base_url: str = "http://localhost:3000"

    # Auth.
    session_cookie_name: str = "ml_session"
    session_cookie_secure: bool = False  # True in staging/production
    session_ttl_hours: int = 24 * 30
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5
    magic_link_ttl_minutes: int = 10
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # Neon Auth (Better Auth) JWT verification. Disabled by default; when
    # enabled, JWT-shaped bearers verify against the JWKS (inline JSON wins,
    # else fetched + cached from the URL) and map to local users.
    neon_auth_enabled: bool = False
    neon_auth_base_url: str = ""
    neon_auth_jwks_url: str = ""
    neon_auth_jwks_json: str = ""
    neon_auth_issuer: str = ""
    neon_auth_audience: str = ""
    neon_auth_jwks_ttl_seconds: int = 3600

    # Jobs. driver=memory executes eagerly in-process (dev/tests);
    # driver=arq uses Redis-backed workers.
    jobs_driver: Literal["memory", "arq"] = "memory"

    # AI Studio. provider=openrouter routes through the OpenAI-compatible
    # API; provider=fake uses deterministic local stubs (tests/dev).
    ai_provider: Literal["openrouter", "fake"] = "openrouter"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ai_text_model: str = "openai/gpt-4o-mini"
    ai_vision_model: str = "openai/gpt-4o-mini"
    ai_audio_model: str = "openai/whisper-large-v3"
    ai_image_model: str = ""
    ai_video_model: str = ""
    ai_audio_supported: bool = False
    ai_max_job_cost_usd: float = 0.50
    # OpenRouter env aliases (used when set in .env).
    openrouter_text_model: str = ""
    openrouter_vision_model: str = ""
    openrouter_transcription_model: str = ""
    openrouter_image_model: str = ""
    openrouter_video_model: str = ""
    openrouter_max_job_cost_usd: float | None = None
    ai_timeout_seconds: int = 120
    ai_max_output_tokens: int = 2000
    ai_max_attempts: int = 3
    ai_retry_base_seconds: float = 2.0
    free_monthly_ai_tokens: int = 100_000
    premium_monthly_ai_tokens: int = 5_000_000

    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, value: Any) -> list[str]:
        import json

        if value is None:
            return ["http://localhost:3000"]
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return ["http://localhost:3000"]
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        return [str(v).strip() for v in parsed if str(v).strip()]
                except json.JSONDecodeError:
                    raw = raw.strip("[]")
            return [
                item.strip().strip('"').strip("'")
                for item in raw.split(",")
                if item.strip().strip('"').strip("'")
            ]
        return [str(value)]

    @field_validator("database_url", mode="before")
    @classmethod
    def _check_db_scheme(cls, value: str) -> str:
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith("postgres://"):
                raw = "postgresql+asyncpg://" + raw[len("postgres://") :]
            elif raw.startswith("postgresql://"):
                raw = "postgresql+asyncpg://" + raw[len("postgresql://") :]
            if not raw.startswith(
                ("postgresql+asyncpg://", "postgresql+psycopg://", "sqlite+aiosqlite://")
            ):
                raise ValueError(
                    "database_url must use postgresql+asyncpg, postgresql+psycopg, or sqlite+aiosqlite"
                )
            return raw
        return value

    @field_validator("session_cookie_secure")
    @classmethod
    def _secure_cookie_in_prod(cls, value: bool, info) -> bool:
        env = (info.data or {}).get("environment", "local")
        if env in {"staging", "production"} and not value:
            raise ValueError("session_cookie_secure must be true outside local/test")
        return value

    @model_validator(mode="after")
    def _normalize_provider_aliases(self) -> Settings:
        from urllib.parse import urlsplit

        if not self.s3_endpoint_url and self.aws_endpoint_url_s3:
            self.s3_endpoint_url = self.aws_endpoint_url_s3
        if not self.s3_access_key and self.aws_access_key_id:
            self.s3_access_key = self.aws_access_key_id
        if not self.s3_secret_key and self.aws_secret_access_key:
            self.s3_secret_key = self.aws_secret_access_key
        if (not self.s3_region or self.s3_region == "auto") and self.aws_region:
            self.s3_region = self.aws_region

        if self.openrouter_text_model:
            self.ai_text_model = self.openrouter_text_model
        if self.openrouter_vision_model:
            self.ai_vision_model = self.openrouter_vision_model
        if self.openrouter_transcription_model:
            self.ai_audio_model = self.openrouter_transcription_model
        if self.openrouter_image_model:
            self.ai_image_model = self.openrouter_image_model
        if self.openrouter_video_model:
            self.ai_video_model = self.openrouter_video_model
        if self.openrouter_max_job_cost_usd is not None:
            self.ai_max_job_cost_usd = self.openrouter_max_job_cost_usd

        if self.neon_auth_base_url:
            parts = urlsplit(self.neon_auth_base_url.strip())
            if parts.scheme and parts.netloc:
                origin = f"{parts.scheme}://{parts.netloc}"
                if not self.neon_auth_issuer and "neon_auth_issuer" not in self.model_fields_set:
                    self.neon_auth_issuer = origin
                if not self.neon_auth_audience and "neon_auth_audience" not in self.model_fields_set:
                    self.neon_auth_audience = origin
            if not self.neon_auth_jwks_url and "neon_auth_jwks_url" not in self.model_fields_set:
                self.neon_auth_jwks_url = (
                    f"{self.neon_auth_base_url.rstrip('/')}/.well-known/jwks.json"
                )
        return self

    # NB: openrouter_api_key is validated at AI invocation time (the
    # provider raises a clear error), not at startup, so API-only processes
    # boot without AI credentials.
    @property
    def uses_redis(self) -> bool:
        return bool(self.redis_url)

    @property
    def is_test(self) -> bool:
        return self.environment == "test"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def reset_settings_cache() -> None:
    get_settings.cache_clear()

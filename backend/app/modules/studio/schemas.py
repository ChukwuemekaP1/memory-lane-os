"""Studio schemas (API_SPECIFICATION Section 11)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AIJobCreateIn(StrictModel):
    kind: str
    inputs: dict = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=120)


class AIAssetPatchIn(StrictModel):
    title: str | None = Field(default=None, max_length=200)
    text_body: str | None = None

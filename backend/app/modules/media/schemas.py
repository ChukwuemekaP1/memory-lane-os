"""Media schemas (API_SPECIFICATION Section 10)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PresignIn(StrictModel):
    space_id: UUID
    mime: str = Field(min_length=3, max_length=100)
    bytes: int = Field(gt=0, le=2_147_483_648)
    kind: str | None = Field(default=None, max_length=10)


class ConfirmIn(StrictModel):
    asset_id: UUID

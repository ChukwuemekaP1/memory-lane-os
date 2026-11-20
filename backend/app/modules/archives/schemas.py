"""Archive schemas (API_SPECIFICATION Section 14)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ArchiveCreateIn(StrictModel):
    kind: str
    options: dict = Field(default_factory=dict)


class CloseAccountIn(StrictModel):
    confirm_email: str = Field(max_length=254)


class PurgeAccountIn(StrictModel):
    confirm_email: str = Field(max_length=254)

"""Contribution schemas (API_SPECIFICATION Sections 9 + 13)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ContributionCreateIn(StrictModel):
    kind: str
    body: str | None = Field(default=None, max_length=20000)
    guest_name: str | None = Field(default=None, min_length=1, max_length=80)
    is_anonymous: bool = False
    is_private_to_owner: bool = False
    taken_at: datetime | None = None
    asset_ids: list[UUID] = Field(default_factory=list, max_length=10)


class ContributionPatchIn(StrictModel):
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    taken_at: datetime | None = None


class ReactionIn(StrictModel):
    emoji: str = Field(min_length=1, max_length=16)


class ReplyCreateIn(StrictModel):
    body: str = Field(min_length=1, max_length=2000)
    guest_name: str | None = Field(default=None, min_length=1, max_length=80)


class ReportIn(StrictModel):
    reason: str = Field(min_length=1, max_length=500)


class TagCreateIn(StrictModel):
    label: str = Field(min_length=1, max_length=80)
    user_id: UUID | None = None


class ModerationActionIn(StrictModel):
    reason: str | None = Field(default=None, max_length=500)


class ContributionListQuery(StrictModel):
    kind: str | None = None
    q: str | None = Field(default=None, max_length=200)
    taken_from: datetime | None = None
    taken_to: datetime | None = None
    author: str | None = Field(default=None, max_length=80)
    sort: str = "-created_at"
    cursor: str | None = None
    limit: int | None = Field(default=None, ge=1, le=100)

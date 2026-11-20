"""Scheduling schemas (API_SPECIFICATION Section 12)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ScheduleCreateIn(StrictModel):
    kind: str
    run_at: datetime
    timezone: str | None = Field(default=None, max_length=60)
    payload: dict = Field(default_factory=dict)


class RescheduleIn(StrictModel):
    run_at: datetime


class ReminderPrefsIn(StrictModel):
    digest_enabled: bool | None = None
    reminder_enabled: bool | None = None

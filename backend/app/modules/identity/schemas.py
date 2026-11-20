"""Identity request/response schemas (API_SPECIFICATION Section 6)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RequestCodeIn(StrictModel):
    email: EmailStr = Field(max_length=254)


class RequestCodeOut(StrictModel):
    masked_email: str


class VerifyCodeIn(StrictModel):
    email: EmailStr = Field(max_length=254)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class UserOut(StrictModel):
    id: UUID
    email: str
    display_name: str
    email_verified_at: datetime | None
    role_global: str


class SessionOut(StrictModel):
    user: UserOut
    session_expires_at: datetime


class GuestActorOut(StrictModel):
    type: str = "guest"
    space_id: UUID
    role_cap: str
    label: str


class UserActorOut(StrictModel):
    type: str = "user"
    user: UserOut


class MeOut(StrictModel):
    actor: UserActorOut | GuestActorOut | None

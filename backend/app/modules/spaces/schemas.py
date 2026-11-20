"""Spaces request/response schemas (API_SPECIFICATION Sections 7-8)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SpaceCreateIn(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    kind: str = Field(default="event", max_length=20)
    occasion: str = Field(default="other", max_length=40)
    theme_id: UUID
    visibility: str = "private"
    contribution_policy: str = "link_contributors"
    moderation_mode: str = "post"
    allow_anonymous: bool = True
    allow_viewer_react: bool = False
    ai_opt_in: bool = False
    event_date: date | None = None
    publish_at: datetime | None = None
    location_label: str | None = Field(default=None, max_length=200)
    timezone: str = Field(default="Africa/Lagos", max_length=60)


class SpacePatchIn(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    kind: str | None = Field(default=None, max_length=20)
    occasion: str | None = Field(default=None, max_length=40)
    theme_id: UUID | None = None
    theme_overrides: dict | None = None
    visibility: str | None = None
    contribution_policy: str | None = None
    moderation_mode: str | None = None
    allow_anonymous: bool | None = None
    allow_viewer_react: bool | None = None
    ai_opt_in: bool | None = None
    event_date: date | None = None
    publish_at: datetime | None = None
    location_label: str | None = Field(default=None, max_length=200)
    timezone: str | None = Field(default=None, max_length=60)
    cover_asset_id: UUID | None = None


class SpaceSettingsPatchIn(StrictModel):
    reminder_enabled: bool | None = None
    reminder_days_before: list[int] | None = None
    digest_enabled: bool | None = None
    letter_delivery_timezone: str | None = Field(default=None, max_length=60)
    default_reply_notify: bool | None = None


class SpaceSettingsOut(StrictModel):
    reminder_enabled: bool
    reminder_days_before: list[int]
    digest_enabled: bool
    letter_delivery_timezone: str
    default_reply_notify: bool


class ThemeOut(StrictModel):
    id: UUID
    slug: str
    name: str
    occasions: list[str]
    tokens: dict
    plan_required: str
    entitled: bool = True


class ResolvedThemeOut(StrictModel):
    theme: ThemeOut
    tokens: dict  # base tokens merged with space overrides
    is_customized: bool


class SpaceOut(StrictModel):
    id: UUID
    owner_id: UUID
    title: str
    description: str | None
    kind: str
    occasion: str
    visibility: str
    contribution_policy: str
    moderation_mode: str
    allow_anonymous: bool
    allow_viewer_react: bool
    ai_opt_in: bool
    event_date: date | None
    publish_at: datetime | None
    location_label: str | None
    timezone: str
    storage_quota_bytes: int
    storage_used_bytes: int
    created_at: datetime
    deleted_at: datetime | None = None


class SpaceDetailOut(StrictModel):
    space: SpaceOut
    theme: ResolvedThemeOut
    settings: SpaceSettingsOut | None
    stats: dict
    my_role: str | None  # owner/collaborator/contributor/viewer/guest/None
    my_permissions: list[str]
    preview: bool = False  # staff preview of unpublished scheduled space


class GuestTokenMintIn(StrictModel):
    label: str = Field(min_length=1, max_length=80)
    role_cap: str = "contributor"
    max_uses: int | None = Field(default=None, ge=1, le=1000000)
    expires_at: datetime | None = None


class GuestTokenOut(StrictModel):
    id: UUID
    label: str
    role_cap: str
    use_count: int
    max_uses: int | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class GuestTokenMintOut(StrictModel):
    token: GuestTokenOut
    url: str
    qr_payload: str
    token_preview: str  # first 8 chars; the raw token is never returned again


class MembershipOut(StrictModel):
    user_id: UUID
    email: str
    display_name: str
    role: str
    created_at: datetime


class MembershipPatchIn(StrictModel):
    role: str


class InvitationCreateIn(StrictModel):
    email: str = Field(max_length=254)
    role: str


class InvitationOut(StrictModel):
    id: UUID
    email: str
    role: str
    accepted_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class PurgeIn(StrictModel):
    confirm_title: str = Field(min_length=1, max_length=120)


class TransferIn(StrictModel):
    new_owner_user_id: UUID


class ThemePreviewIn(StrictModel):
    theme_id: UUID | None = None
    overrides: dict | None = None

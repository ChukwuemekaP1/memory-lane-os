"""Space aggregate: spaces, memberships, guest tokens, invitations, themes (Section 4)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.models.enums import (
    ContributionPolicy,
    GuestRoleCap,
    ModerationMode,
    Plan,
    SpaceRole,
    SpaceVisibility,
    plan_enum,
)

if TYPE_CHECKING:
    from app.models.users import User

# Shared Enum instances: reusing one type object per PG enum name prevents
# duplicate CREATE TYPE statements when several tables share the enum.
_space_role_enum = Enum(SpaceRole, name="space_role", native_enum=True)


class Theme(Base, IdMixin, TimestampMixin):
    __tablename__ = "themes"

    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    occasions: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    tokens: Mapped[dict] = mapped_column(JSONB, nullable=False)
    plan_required: Mapped[Plan] = mapped_column(plan_enum, default=Plan.free, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    spaces: Mapped[list[Space]] = relationship(back_populates="theme", lazy="raise")


class Space(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "spaces"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, default="event", nullable=False)
    occasion: Mapped[str] = mapped_column(Text, nullable=False)
    theme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("themes.id", ondelete="RESTRICT"), nullable=False
    )
    visibility: Mapped[SpaceVisibility] = mapped_column(
        Enum(SpaceVisibility, name="space_visibility", native_enum=True),
        default=SpaceVisibility.private,
        nullable=False,
    )
    contribution_policy: Mapped[ContributionPolicy] = mapped_column(
        Enum(ContributionPolicy, name="contribution_policy", native_enum=True),
        default=ContributionPolicy.link_contributors,
        nullable=False,
    )
    moderation_mode: Mapped[ModerationMode] = mapped_column(
        Enum(ModerationMode, name="moderation_mode", native_enum=True),
        default=ModerationMode.post,
        nullable=False,
    )
    allow_anonymous: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_viewer_react: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date)
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location_label: Mapped[str | None] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(Text, default="Africa/Lagos", nullable=False)
    theme_overrides: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    cover_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    storage_quota_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_used_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    theme: Mapped[Theme] = relationship(back_populates="spaces", lazy="raise")
    memberships: Mapped[list[SpaceMembership]] = relationship(back_populates="space", lazy="raise")
    guest_tokens: Mapped[list[GuestAccessToken]] = relationship(back_populates="space", lazy="raise")
    settings: Mapped[SpaceSettings | None] = relationship(back_populates="space", lazy="raise")

    __table_args__ = (
        Index("ix_spaces_owner_created", "owner_id", "created_at"),
        Index(
            "ix_spaces_publish_at",
            "publish_at",
            postgresql_where="publish_at IS NOT NULL AND deleted_at IS NULL",
        ),
        Index("ix_spaces_occasion", "occasion"),
        CheckConstraint("char_length(title) BETWEEN 1 AND 120", name="title_length"),
        CheckConstraint("storage_used_bytes >= 0", name="storage_used_nonneg"),
        CheckConstraint(
            "kind IN ('event', 'ongoing', 'personal', 'relationship', 'family', 'group',"
            " 'custom')",
            name="kind_valid",
        ),
    )


class SpaceMembership(Base, IdMixin, TimestampMixin):
    __tablename__ = "space_memberships"

    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[SpaceRole] = mapped_column(_space_role_enum, nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    space: Mapped[Space] = relationship(back_populates="memberships", lazy="raise")
    user: Mapped[User] = relationship(
        back_populates="memberships", lazy="raise", foreign_keys="SpaceMembership.user_id"
    )

    __table_args__ = (
        Index("uq_space_memberships_space_user", "space_id", "user_id", unique=True),
        Index("ix_space_memberships_user", "user_id"),
    )


class GuestAccessToken(Base, IdMixin, TimestampMixin):
    __tablename__ = "guest_access_tokens"

    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    role_cap: Mapped[GuestRoleCap] = mapped_column(
        Enum(GuestRoleCap, name="guest_role_cap", native_enum=True),
        default=GuestRoleCap.contributor,
        nullable=False,
    )
    max_uses: Mapped[int | None] = mapped_column(Integer)
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_by_email: Mapped[str | None] = mapped_column(CITEXT())

    space: Mapped[Space] = relationship(back_populates="guest_tokens", lazy="raise")

    __table_args__ = (
        Index("ix_guest_tokens_space_revoked", "space_id", "revoked_at"),
        CheckConstraint("use_count >= 0", name="use_count_nonneg"),
    )


class Invitation(Base, IdMixin, TimestampMixin):
    __tablename__ = "invitations"

    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    role: Mapped[SpaceRole] = mapped_column(_space_role_enum, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "uq_invitations_pending",
            "space_id",
            "email",
            unique=True,
            postgresql_where="accepted_at IS NULL AND revoked_at IS NULL",
        ),
    )


class SpaceSettings(Base, TimestampMixin):
    __tablename__ = "space_settings"

    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), primary_key=True
    )
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reminder_days_before: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=lambda: [7, 1], nullable=False
    )
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    letter_delivery_timezone: Mapped[str] = mapped_column(Text, nullable=False)
    default_reply_notify: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    space: Mapped[Space] = relationship(back_populates="settings", lazy="raise")

"""Identity tables: users, sessions, OTP challenges (DATABASE_DESIGN Section 3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import CITEXT, INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.models.enums import GlobalRole

if TYPE_CHECKING:
    from app.models.spaces import SpaceMembership


class User(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    role_global: Mapped[GlobalRole] = mapped_column(
        Enum(GlobalRole, name="global_role", native_enum=True), default=GlobalRole.user, nullable=False
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locale: Mapped[str] = mapped_column(Text, default="en", nullable=False)
    timezone: Mapped[str] = mapped_column(Text, default="Africa/Lagos", nullable=False)
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    neon_auth_sub: Mapped[str | None] = mapped_column(Text, unique=True, default=None)

    sessions: Mapped[list[UserSession]] = relationship(back_populates="user", lazy="raise")
    memberships: Mapped[list[SpaceMembership]] = relationship(
        back_populates="user", lazy="raise", foreign_keys="SpaceMembership.user_id"
    )

    __table_args__ = (Index("ix_users_created_at", "created_at"),)


class UserSession(Base, IdMixin, TimestampMixin):
    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    refresh_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    device_label: Mapped[str | None] = mapped_column(String(200))
    ip_created: Mapped[str | None] = mapped_column(INET())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="sessions", lazy="raise")

    __table_args__ = (Index("ix_user_sessions_user_revoked", "user_id", "revoked_at"),)


class OtpChallenge(Base, IdMixin, TimestampMixin):
    __tablename__ = "otp_challenges"

    email: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    magic_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_request: Mapped[str | None] = mapped_column(INET())

    __table_args__ = (Index("ix_otp_challenges_email_expires", "email", "expires_at"),)

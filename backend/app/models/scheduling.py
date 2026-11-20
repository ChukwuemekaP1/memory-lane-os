"""Scheduling and notification tables (DATABASE_DESIGN Section 8)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, SmallInteger, Text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import NotificationKind, NotificationStatus, ScheduledKind, ScheduledStatus


class ScheduledEvent(Base, IdMixin, TimestampMixin):
    __tablename__ = "scheduled_events"

    space_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    kind: Mapped[ScheduledKind] = mapped_column(
        Enum(ScheduledKind, name="scheduled_kind", native_enum=True), nullable=False
    )
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[ScheduledStatus] = mapped_column(
        Enum(ScheduledStatus, name="scheduled_status", native_enum=True),
        default=ScheduledStatus.scheduled,
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    claimed_by: Mapped[str | None] = mapped_column(Text)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_sched_due", "run_at", postgresql_where="status = 'scheduled'"),
        Index("ix_sched_space_kind", "space_id", "kind"),
        Index("ix_sched_user_kind", "user_id", "kind"),
        CheckConstraint("space_id IS NOT NULL OR user_id IS NOT NULL", name="sched_scope"),
    )


class Notification(Base, IdMixin, TimestampMixin):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    space_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE")
    )
    kind: Mapped[NotificationKind] = mapped_column(
        Enum(NotificationKind, name="notification_kind", native_enum=True), nullable=False
    )
    template: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status", native_enum=True),
        default=NotificationStatus.queued,
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    provider_msg_id: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "ix_notif_status",
            "status",
            postgresql_where="status IN ('queued', 'sending', 'failed')",
        ),
        Index("ix_notif_user_created", "user_id", "created_at"),
        Index("ix_notif_email_kind_created", "email", "kind", "created_at"),
    )

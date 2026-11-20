"""Interactions and moderation tables (DATABASE_DESIGN Section 6)."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.models.enums import ModerationAction, ModerationTarget, ReplyStatus, TagStatus


class Reaction(Base, IdMixin, TimestampMixin):
    __tablename__ = "reactions"

    contribution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contributions.id", ondelete="CASCADE"), nullable=False
    )
    reactor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    guest_token_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guest_access_tokens.id", ondelete="CASCADE")
    )
    emoji: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        Index("ix_reactions_contribution", "contribution_id"),
        Index(
            "uq_reactions_user_emoji",
            "contribution_id",
            "reactor_user_id",
            "emoji",
            unique=True,
            postgresql_where="reactor_user_id IS NOT NULL",
        ),
        Index(
            "uq_reactions_guest_emoji",
            "contribution_id",
            "guest_token_id",
            "emoji",
            unique=True,
            postgresql_where="guest_token_id IS NOT NULL",
        ),
        CheckConstraint(
            "reactor_user_id IS NOT NULL OR guest_token_id IS NOT NULL", name="reactor_present"
        ),
    )


class Reply(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "replies"

    contribution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contributions.id", ondelete="CASCADE"), nullable=False
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    guest_token_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guest_access_tokens.id", ondelete="SET NULL")
    )
    guest_name: Mapped[str | None] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReplyStatus] = mapped_column(
        Enum(ReplyStatus, name="reply_status", native_enum=True),
        default=ReplyStatus.visible,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_replies_contribution_created", "contribution_id", "created_at"),
        CheckConstraint(
            "author_user_id IS NOT NULL OR guest_token_id IS NOT NULL OR guest_name IS NOT NULL",
            name="reply_attributable",
        ),
        CheckConstraint("char_length(body) BETWEEN 1 AND 2000", name="reply_body_len"),
    )


class ModerationRecord(Base, IdMixin, TimestampMixin):
    __tablename__ = "moderation_records"

    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[ModerationTarget] = mapped_column(
        Enum(ModerationTarget, name="moderation_target", native_enum=True), nullable=False
    )
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[ModerationAction] = mapped_column(
        Enum(ModerationAction, name="moderation_action", native_enum=True), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(String(500))
    acted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    rule: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_moderation_space_created", "space_id", "created_at"),
        Index("ix_moderation_target", "target_type", "target_id"),
    )


class ContributionTag(Base, IdMixin, TimestampMixin):
    __tablename__ = "contribution_tags"

    contribution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contributions.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    suggested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    suggested_by_token_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guest_access_tokens.id", ondelete="SET NULL")
    )
    status: Mapped[TagStatus] = mapped_column(
        Enum(TagStatus, name="tag_status", native_enum=True), nullable=False
    )

    __table_args__ = (
        Index("ix_tags_contribution", "contribution_id"),
        Index("ix_tags_user_status", "user_id", "status"),
    )

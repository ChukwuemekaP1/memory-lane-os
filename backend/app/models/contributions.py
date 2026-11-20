"""Contributions and media tables (DATABASE_DESIGN Section 5)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.models.enums import (
    ContributionKind,
    ContributionStatus,
    JobStatus,
    MediaKind,
    MediaStatus,
)


class Contribution(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "contributions"

    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    guest_token_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guest_access_tokens.id", ondelete="SET NULL")
    )
    guest_name: Mapped[str | None] = mapped_column(String(80))
    author_snapshot: Mapped[str | None] = mapped_column(String(80))
    kind: Mapped[ContributionKind] = mapped_column(
        Enum(ContributionKind, name="contribution_kind", native_enum=True), nullable=False
    )
    body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ContributionStatus] = mapped_column(
        Enum(ContributionStatus, name="contribution_status", native_enum=True),
        default=ContributionStatus.visible,
        nullable=False,
    )
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_private_to_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_categories: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(Text)

    attachments: Mapped[list[ContributionAttachment]] = relationship(
        back_populates="contribution", lazy="raise"
    )

    __table_args__ = (
        Index("ix_contributions_space_status_created", "space_id", "status", "created_at"),
        Index("ix_contributions_space_taken", "space_id", "taken_at"),
        Index("ix_contributions_author", "author_user_id"),
        Index(
            "uq_contributions_space_idem",
            "space_id",
            "idempotency_key",
            unique=True,
            postgresql_where="idempotency_key IS NOT NULL",
        ),
        Index(
            "ix_contributions_body_trgm",
            "body",
            postgresql_using="gin",
            postgresql_ops={"body": "gin_trgm_ops"},
        ),
        CheckConstraint(
            "author_user_id IS NOT NULL OR guest_token_id IS NOT NULL OR guest_name IS NOT NULL",
            name="attributable",
        ),
        CheckConstraint(
            "NOT (is_private_to_owner AND kind = 'future_letter')", name="no_private_letter"
        ),
        CheckConstraint("body IS NULL OR char_length(body) <= 20000", name="body_maxlen"),
    )


class MediaAsset(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "media_assets"

    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    uploader_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    guest_token_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guest_access_tokens.id", ondelete="SET NULL")
    )
    kind: Mapped[MediaKind] = mapped_column(
        Enum(MediaKind, name="media_kind", native_enum=True), nullable=False
    )
    original_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    original_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_mime: Mapped[str] = mapped_column(Text, nullable=False)
    original_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    derivatives: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[MediaStatus] = mapped_column(
        Enum(MediaStatus, name="media_status", native_enum=True),
        default=MediaStatus.reserved,
        nullable=False,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    exif_stripped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    processing_jobs: Mapped[list[MediaProcessingJob]] = relationship(
        back_populates="asset", lazy="raise"
    )

    __table_args__ = (
        Index("ix_media_assets_space_status", "space_id", "status"),
        Index("ix_media_assets_sha256", "original_sha256"),
        Index(
            "ix_media_assets_space_live",
            "space_id",
            postgresql_where="deleted_at IS NULL",
        ),
        CheckConstraint("original_bytes > 0", name="bytes_positive"),
    )


class MediaProcessingJob(Base, IdMixin, TimestampMixin):
    __tablename__ = "media_processing_jobs"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", native_enum=True),
        default=JobStatus.queued,
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    asset: Mapped[MediaAsset] = relationship(back_populates="processing_jobs", lazy="raise")

    __table_args__ = (
        Index("ix_media_jobs_asset", "asset_id"),
        Index(
            "ix_media_jobs_status",
            "status",
            postgresql_where="status IN ('queued', 'running', 'failed')",
        ),
    )


class ContributionAttachment(Base, IdMixin, TimestampMixin):
    __tablename__ = "contribution_attachments"

    contribution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contributions.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    caption: Mapped[str | None] = mapped_column(String(500))

    contribution: Mapped[Contribution] = relationship(back_populates="attachments", lazy="raise")

    __table_args__ = (
        Index("uq_attachments_contrib_asset", "contribution_id", "asset_id", unique=True),
    )

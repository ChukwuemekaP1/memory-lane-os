"""AI Memory Studio tables (DATABASE_DESIGN Section 7)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Numeric, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.models.enums import AIJobStatus, AIKind

_ai_kind_enum = Enum(AIKind, name="ai_kind", native_enum=True)


class AIGenerationJob(Base, IdMixin, TimestampMixin):
    __tablename__ = "ai_generation_jobs"

    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    requested_by_email: Mapped[str | None] = mapped_column(CITEXT())
    kind: Mapped[AIKind] = mapped_column(_ai_kind_enum, nullable=False)
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    status: Mapped[AIJobStatus] = mapped_column(
        Enum(AIJobStatus, name="ai_job_status", native_enum=True),
        default=AIJobStatus.queued,
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    quota_reserved: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(BigInteger)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    last_error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    outputs: Mapped[list[AIGeneratedAsset]] = relationship(back_populates="job", lazy="raise")

    __table_args__ = (Index("ix_ai_jobs_space_kind_created", "space_id", "kind", "created_at"),)


class AIGeneratedAsset(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "ai_generated_assets"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_generation_jobs.id", ondelete="CASCADE"), nullable=False
    )
    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[AIKind] = mapped_column(_ai_kind_enum, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    text_body: Mapped[str | None] = mapped_column(Text)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    edit_list: Mapped[dict | None] = mapped_column(JSONB)
    is_promoted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_ai_labeled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    job: Mapped[AIGenerationJob] = relationship(back_populates="outputs", lazy="raise")

    __table_args__ = (
        Index("ix_ai_assets_space_kind", "space_id", "kind"),
        Index("ix_ai_assets_job", "job_id"),
    )

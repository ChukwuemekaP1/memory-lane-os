"""Archives and billing tables (DATABASE_DESIGN Section 9)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import (
    ArchiveKind,
    ArchiveStatus,
    BillingProvider,
    MoneyProvider,
    PaymentKind,
    PaymentStatus,
    Plan,
    SubscriptionStatus,
    UsageKind,
    plan_enum,
)


class Archive(Base, IdMixin, TimestampMixin):
    __tablename__ = "archives"

    space_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE")
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    kind: Mapped[ArchiveKind] = mapped_column(
        Enum(ArchiveKind, name="archive_kind", native_enum=True), nullable=False
    )
    status: Mapped[ArchiveStatus] = mapped_column(
        Enum(ArchiveStatus, name="archive_status", native_enum=True),
        default=ArchiveStatus.queued,
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    result_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    download_token_hash: Mapped[str | None] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_archives_space_kind_created", "space_id", "kind", "created_at"),)


class Subscription(Base, IdMixin, TimestampMixin):
    __tablename__ = "subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    plan: Mapped[Plan] = mapped_column(plan_enum, default=Plan.free, nullable=False)
    provider: Mapped[BillingProvider] = mapped_column(
        Enum(BillingProvider, name="billing_provider", native_enum=True),
        default=BillingProvider.none,
        nullable=False,
    )
    provider_customer_id: Mapped[str | None] = mapped_column(Text)
    provider_sub_id: Mapped[str | None] = mapped_column(Text, unique=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status", native_enum=True),
        default=SubscriptionStatus.active,
        nullable=False,
    )
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index(
            "uq_subscriptions_live_user",
            "user_id",
            unique=True,
            postgresql_where="status IN ('active', 'past_due')",
        ),
    )


class Payment(Base, IdMixin, TimestampMixin):
    __tablename__ = "payments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL")
    )
    space_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="SET NULL")
    )
    provider: Mapped[MoneyProvider] = mapped_column(
        Enum(MoneyProvider, name="money_provider", native_enum=True), nullable=False
    )
    provider_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    provider_ref: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[PaymentKind] = mapped_column(
        Enum(PaymentKind, name="payment_kind", native_enum=True), nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=True),
        default=PaymentStatus.pending,
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        Index("uq_payments_provider_event", "provider", "provider_event_id", unique=True),
        Index("ix_payments_user_created", "user_id", "created_at"),
        Index("ix_payments_space", "space_id"),
        CheckConstraint("amount_minor > 0", name="amount_positive"),
    )


class UsageRecord(Base, IdMixin, TimestampMixin):
    __tablename__ = "usage_records"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    space_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="SET NULL")
    )
    kind: Mapped[UsageKind] = mapped_column(
        Enum(UsageKind, name="usage_kind", native_enum=True), nullable=False
    )
    units: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ref_type: Mapped[str | None] = mapped_column(Text)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)

    __table_args__ = (Index("ix_usage_user_kind_created", "user_id", "kind", "created_at"),)

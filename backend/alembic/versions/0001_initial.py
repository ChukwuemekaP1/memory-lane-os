"""Initial schema: all 24 tables (DATABASE_DESIGN), PG extensions, enums.

Deferred FKs (cycles): users.avatar_asset_id and spaces.cover_asset_id are
added after media_assets exists. Seeds live in the follow-up data migration.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


ENUMS: dict[str, postgresql.ENUM] = {
        "global_role": postgresql.ENUM("user", "admin", name="global_role", create_type=False),
        "plan": postgresql.ENUM("free", "premium", name="plan", create_type=False),
        "space_visibility": postgresql.ENUM("private", "link", "scheduled", name="space_visibility", create_type=False),
        "contribution_policy": postgresql.ENUM(
            "owner_only", "members", "link_contributors", "anyone_with_link",
            name="contribution_policy", create_type=False),
        "moderation_mode": postgresql.ENUM("post", "pre", name="moderation_mode", create_type=False),
        "space_role": postgresql.ENUM("collaborator", "contributor", "viewer", name="space_role", create_type=False),
        "guest_role_cap": postgresql.ENUM("viewer", "contributor", name="guest_role_cap", create_type=False),
        "contribution_kind": postgresql.ENUM(
            "message", "story", "media", "audio", "private_note", "future_letter",
            name="contribution_kind", create_type=False),
        "contribution_status": postgresql.ENUM(
            "pending", "visible", "hidden", "rejected", name="contribution_status", create_type=False),
        "media_kind": postgresql.ENUM("image", "video", "audio", "other", name="media_kind", create_type=False),
        "media_status": postgresql.ENUM(
            "reserved", "uploaded", "processing", "ready", "failed", name="media_status", create_type=False),
        "job_status": postgresql.ENUM(
            "queued", "running", "succeeded", "failed", "dead", name="job_status", create_type=False),
        "reply_status": postgresql.ENUM("visible", "hidden", name="reply_status", create_type=False),
        "moderation_target": postgresql.ENUM("contribution", "reply", name="moderation_target", create_type=False),
        "moderation_action": postgresql.ENUM(
            "approve", "hide", "reject", "restore", name="moderation_action", create_type=False),
        "ai_kind": postgresql.ENUM(
            "transcription", "categorization", "captions", "summary", "letter", "book",
            "highlight_film", name="ai_kind", create_type=False),
        "ai_job_status": postgresql.ENUM(
            "queued", "running", "succeeded", "failed", "dead", "cancelled", name="ai_job_status", create_type=False),
        "scheduled_kind": postgresql.ENUM(
            "reveal", "reminder", "future_letter", "capsule", "digest", name="scheduled_kind", create_type=False),
        "scheduled_status": postgresql.ENUM(
            "scheduled", "claimed", "running", "done", "failed", "dead", "cancelled",
            name="scheduled_status", create_type=False),
        "notification_kind": postgresql.ENUM(
            "otp", "invite", "contribution", "reply", "reaction_digest", "reveal", "reminder",
            "letter", "export_ready", "billing", "system", name="notification_kind", create_type=False),
        "notification_status": postgresql.ENUM(
            "queued", "sending", "sent", "failed", "dead", "skipped_prefs",
            name="notification_status", create_type=False),
        "archive_kind": postgresql.ENUM(
            "full_zip", "book_pdf", "film_mp4", "data_export", "purge", name="archive_kind", create_type=False),
        "archive_status": postgresql.ENUM(
            "queued", "running", "succeeded", "failed", "dead", "expired", name="archive_status", create_type=False),
        "billing_provider": postgresql.ENUM("paystack", "stripe", "none", name="billing_provider", create_type=False),
        "money_provider": postgresql.ENUM("paystack", "stripe", name="money_provider", create_type=False),
        "subscription_status": postgresql.ENUM(
            "active", "past_due", "cancelled", "expired", name="subscription_status", create_type=False),
        "payment_kind": postgresql.ENUM(
            "subscription", "renewal", "one_time", "refund", name="payment_kind", create_type=False),
        "payment_status": postgresql.ENUM(
            "pending", "succeeded", "failed", "refunded", name="payment_status", create_type=False),
        "usage_kind": postgresql.ENUM(
            "ai_text", "ai_vision", "ai_transcription", "ai_film", "storage", "export",
            name="usage_kind", create_type=False),
    }


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for enum in ENUMS.values():
        enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("avatar_asset_id", postgresql.UUID(as_uuid=True)),  # FK added later (cycle)
        sa.Column("role_global", ENUMS["global_role"], nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("locale", sa.Text, nullable=False),
        sa.Column("timezone", sa.Text, nullable=False),
        sa.Column("marketing_opt_in", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_created_at", "users", ["created_at"])

    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("refresh_hash", sa.Text, nullable=False, unique=True),
        sa.Column("device_label", sa.String(200)),
        sa.Column("ip_created", postgresql.INET()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_user_sessions_user_revoked", "user_sessions", ["user_id", "revoked_at"])

    op.create_table(
        "otp_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("code_hash", sa.Text, nullable=False),
        sa.Column("magic_hash", sa.Text, nullable=False, unique=True),
        sa.Column("attempts", sa.SmallInteger, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("ip_request", postgresql.INET()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_otp_challenges_email_expires", "otp_challenges", ["email", "expires_at"])

    op.create_table(
        "themes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("occasions", postgresql.ARRAY(sa.Text), nullable=False),
        sa.Column("tokens", postgresql.JSONB, nullable=False),
        sa.Column("plan_required", ENUMS["plan"], nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "spaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("occasion", sa.Text, nullable=False),
        sa.Column(
            "theme_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("themes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("visibility", ENUMS["space_visibility"], nullable=False),
        sa.Column("contribution_policy", ENUMS["contribution_policy"], nullable=False),
        sa.Column("moderation_mode", ENUMS["moderation_mode"], nullable=False),
        sa.Column("allow_anonymous", sa.Boolean, nullable=False),
        sa.Column("allow_viewer_react", sa.Boolean, nullable=False),
        sa.Column("ai_opt_in", sa.Boolean, nullable=False),
        sa.Column("event_date", sa.Date),
        sa.Column("publish_at", sa.DateTime(timezone=True)),
        sa.Column("location_label", sa.String(200)),
        sa.Column("cover_asset_id", postgresql.UUID(as_uuid=True)),  # FK added later (cycle)
        sa.Column("storage_quota_bytes", sa.BigInteger, nullable=False),
        sa.Column("storage_used_bytes", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 120", name="ck_spaces_title_length"),
        sa.CheckConstraint("storage_used_bytes >= 0", name="ck_spaces_storage_used_nonneg"),
    )
    op.create_index("ix_spaces_owner_created", "spaces", ["owner_id", "created_at"])
    op.create_index(
        "ix_spaces_publish_at", "spaces", ["publish_at"],
        postgresql_where=sa.text("publish_at IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index("ix_spaces_occasion", "spaces", ["occasion"])

    op.create_table(
        "space_settings",
        sa.Column(
            "space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("reminder_enabled", sa.Boolean, nullable=False),
        sa.Column("reminder_days_before", postgresql.ARRAY(sa.Integer), nullable=False),
        sa.Column("digest_enabled", sa.Boolean, nullable=False),
        sa.Column("letter_delivery_timezone", sa.Text, nullable=False),
        sa.Column("default_reply_notify", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "space_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", ENUMS["space_role"], nullable=False),
        sa.Column(
            "invited_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "uq_space_memberships_space_user", "space_memberships", ["space_id", "user_id"],
        unique=True,
    )
    op.create_index("ix_space_memberships_user", "space_memberships", ["user_id"])

    op.create_table(
        "guest_access_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("role_cap", ENUMS["guest_role_cap"], nullable=False),
        sa.Column("max_uses", sa.Integer),
        sa.Column("use_count", sa.Integer, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("created_by_email", postgresql.CITEXT()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("use_count >= 0", name="ck_guest_access_tokens_use_count_nonneg"),
    )
    op.create_index(
        "ix_guest_tokens_space_revoked", "guest_access_tokens", ["space_id", "revoked_at"]
    )

    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("role", ENUMS["space_role"], nullable=False),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column(
            "invited_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "uq_invitations_pending", "invitations", ["space_id", "email"], unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )

    op.create_table(
        "contributions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "guest_token_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guest_access_tokens.id", ondelete="SET NULL"),
        ),
        sa.Column("guest_name", sa.String(80)),
        sa.Column("author_snapshot", sa.String(80)),
        sa.Column("kind", ENUMS["contribution_kind"], nullable=False),
        sa.Column("body", sa.Text),
        sa.Column("status", ENUMS["contribution_status"], nullable=False),
        sa.Column("is_anonymous", sa.Boolean, nullable=False),
        sa.Column("is_private_to_owner", sa.Boolean, nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True)),
        sa.Column("idempotency_key", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "author_user_id IS NOT NULL OR guest_token_id IS NOT NULL OR guest_name IS NOT NULL",
            name="ck_contributions_attributable"),
        sa.CheckConstraint(
            "NOT (is_private_to_owner AND kind = 'future_letter')",
            name="ck_contributions_no_private_letter"),
        sa.CheckConstraint(
            "body IS NULL OR char_length(body) <= 20000", name="ck_contributions_body_maxlen"
        ),
    )
    op.create_index(
        "ix_contributions_space_status_created", "contributions", ["space_id", "status", "created_at"]
    )
    op.create_index("ix_contributions_space_taken", "contributions", ["space_id", "taken_at"])
    op.create_index("ix_contributions_author", "contributions", ["author_user_id"])
    op.create_index(
        "uq_contributions_space_idem", "contributions", ["space_id", "idempotency_key"],
        unique=True, postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "ix_contributions_body_trgm", "contributions", ["body"],
        postgresql_using="gin", postgresql_ops={"body": "gin_trgm_ops"},
    )

    op.create_table(
        "media_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploader_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "guest_token_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guest_access_tokens.id", ondelete="SET NULL"),
        ),
        sa.Column("kind", ENUMS["media_kind"], nullable=False),
        sa.Column("original_key", sa.Text, nullable=False, unique=True),
        sa.Column("original_bytes", sa.BigInteger, nullable=False),
        sa.Column("original_mime", sa.Text, nullable=False),
        sa.Column("original_sha256", sa.Text, nullable=False),
        sa.Column("derivatives", postgresql.JSONB, nullable=False),
        sa.Column("width", sa.Integer),
        sa.Column("height", sa.Integer),
        sa.Column("duration_ms", sa.BigInteger),
        sa.Column("status", ENUMS["media_status"], nullable=False),
        sa.Column("failure_reason", sa.Text),
        sa.Column("exif_stripped", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("original_bytes > 0", name="ck_media_assets_bytes_positive"),
    )
    op.create_index("ix_media_assets_space_status", "media_assets", ["space_id", "status"])
    op.create_index("ix_media_assets_sha256", "media_assets", ["original_sha256"])
    op.create_index(
        "ix_media_assets_space_live", "media_assets", ["space_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "media_processing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Text, nullable=False, unique=True),
        sa.Column("status", ENUMS["job_status"], nullable=False),
        sa.Column("attempts", sa.SmallInteger, nullable=False),
        sa.Column("last_error", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_media_jobs_asset", "media_processing_jobs", ["asset_id"])
    op.create_index(
        "ix_media_jobs_status", "media_processing_jobs", ["status"],
        postgresql_where=sa.text("status IN ('queued', 'running', 'failed')"),
    )

    op.create_table(
        "contribution_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contribution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contributions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media_assets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("position", sa.SmallInteger, nullable=False),
        sa.Column("caption", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "uq_attachments_contrib_asset", "contribution_attachments",
        ["contribution_id", "asset_id"], unique=True,
    )

    op.create_table(
        "reactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contribution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contributions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reactor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "guest_token_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guest_access_tokens.id", ondelete="CASCADE"),
        ),
        sa.Column("emoji", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint(
            "reactor_user_id IS NOT NULL OR guest_token_id IS NOT NULL",
            name="ck_reactions_reactor_present"),
    )
    op.create_index("ix_reactions_contribution", "reactions", ["contribution_id"])
    op.create_index(
        "uq_reactions_user_emoji", "reactions",
        ["contribution_id", "reactor_user_id", "emoji"], unique=True,
        postgresql_where=sa.text("reactor_user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_reactions_guest_emoji", "reactions",
        ["contribution_id", "guest_token_id", "emoji"], unique=True,
        postgresql_where=sa.text("guest_token_id IS NOT NULL"),
    )

    op.create_table(
        "replies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contribution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contributions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "guest_token_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guest_access_tokens.id", ondelete="SET NULL"),
        ),
        sa.Column("guest_name", sa.String(80)),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("status", ENUMS["reply_status"], nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "author_user_id IS NOT NULL OR guest_token_id IS NOT NULL OR guest_name IS NOT NULL",
            name="ck_replies_reply_attributable"),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 2000", name="ck_replies_reply_body_len"
        ),
    )
    op.create_index("ix_replies_contribution_created", "replies", ["contribution_id", "created_at"])

    op.create_table(
        "moderation_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_type", ENUMS["moderation_target"], nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", ENUMS["moderation_action"], nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column(
            "acted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("rule", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_moderation_space_created", "moderation_records", ["space_id", "created_at"])
    op.create_index(
        "ix_moderation_target", "moderation_records", ["target_type", "target_id"]
    )

    op.create_table(
        "ai_generation_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("requested_by_email", postgresql.CITEXT()),
        sa.Column("kind", ENUMS["ai_kind"], nullable=False),
        sa.Column("inputs", postgresql.JSONB, nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("model", sa.Text),
        sa.Column("status", ENUMS["ai_job_status"], nullable=False),
        sa.Column("attempts", sa.SmallInteger, nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=False, unique=True),
        sa.Column("quota_reserved", sa.BigInteger, nullable=False),
        sa.Column("last_error", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_ai_jobs_space_kind_created", "ai_generation_jobs", ["space_id", "kind", "created_at"]
    )

    op.create_table(
        "ai_generated_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_generation_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", ENUMS["ai_kind"], nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("text_body", sa.Text),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("edit_list", postgresql.JSONB),
        sa.Column("is_promoted", sa.Boolean, nullable=False),
        sa.Column("is_ai_labeled", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_ai_assets_space_kind", "ai_generated_assets", ["space_id", "kind"])
    op.create_index("ix_ai_assets_job", "ai_generated_assets", ["job_id"])

    op.create_table(
        "scheduled_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spaces.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
        ),
        sa.Column("kind", ENUMS["scheduled_kind"], nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("status", ENUMS["scheduled_status"], nullable=False),
        sa.Column("attempts", sa.SmallInteger, nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=False, unique=True),
        sa.Column("claimed_by", sa.Text),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint(
            "space_id IS NOT NULL OR user_id IS NOT NULL", name="ck_scheduled_events_sched_scope"
        ),
    )
    op.create_index(
        "ix_sched_due", "scheduled_events", ["run_at"],
        postgresql_where=sa.text("status = 'scheduled'"),
    )
    op.create_index("ix_sched_space_kind", "scheduled_events", ["space_id", "kind"])
    op.create_index("ix_sched_user_kind", "scheduled_events", ["user_id", "kind"])

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
        ),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column(
            "space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spaces.id", ondelete="CASCADE"),
        ),
        sa.Column("kind", ENUMS["notification_kind"], nullable=False),
        sa.Column("template", sa.Text, nullable=False),
        sa.Column("data", postgresql.JSONB, nullable=False),
        sa.Column("status", ENUMS["notification_status"], nullable=False),
        sa.Column("attempts", sa.SmallInteger, nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=False, unique=True),
        sa.Column("provider_msg_id", sa.Text),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_notif_status", "notifications", ["status"],
        postgresql_where=sa.text("status IN ('queued', 'sending', 'failed')"),
    )
    op.create_index("ix_notif_user_created", "notifications", ["user_id", "created_at"])
    op.create_index(
        "ix_notif_email_kind_created", "notifications", ["email", "kind", "created_at"]
    )

    op.create_table(
        "archives",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("kind", ENUMS["archive_kind"], nullable=False),
        sa.Column("status", ENUMS["archive_status"], nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=False, unique=True),
        sa.Column(
            "result_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("download_token_hash", sa.Text, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_archives_space_kind_created", "archives", ["space_id", "kind", "created_at"])

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("plan", ENUMS["plan"], nullable=False),
        sa.Column("provider", ENUMS["billing_provider"], nullable=False),
        sa.Column("provider_customer_id", sa.Text),
        sa.Column("provider_sub_id", sa.Text, unique=True),
        sa.Column("status", ENUMS["subscription_status"], nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),
        sa.Column("cancel_at_period_end", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "uq_subscriptions_live_user", "subscriptions", ["user_id"], unique=True,
        postgresql_where=sa.text("status IN ('active', 'past_due')"),
    )

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spaces.id", ondelete="SET NULL"),
        ),
        sa.Column("provider", ENUMS["money_provider"], nullable=False),
        sa.Column("provider_event_id", sa.Text, nullable=False),
        sa.Column("provider_ref", sa.Text, nullable=False),
        sa.Column("kind", ENUMS["payment_kind"], nullable=False),
        sa.Column("amount_minor", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False),
        sa.Column("status", ENUMS["payment_status"], nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("amount_minor > 0", name="ck_payments_amount_positive"),
    )
    op.create_index(
        "uq_payments_provider_event", "payments", ["provider", "provider_event_id"], unique=True
    )
    op.create_index("ix_payments_user_created", "payments", ["user_id", "created_at"])
    op.create_index("ix_payments_space", "payments", ["space_id"])

    op.create_table(
        "usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spaces.id", ondelete="SET NULL"),
        ),
        sa.Column("kind", ENUMS["usage_kind"], nullable=False),
        sa.Column("units", sa.BigInteger, nullable=False),
        sa.Column("ref_type", sa.Text),
        sa.Column("ref_id", postgresql.UUID(as_uuid=True)),
        sa.Column("idempotency_key", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_usage_user_kind_created", "usage_records", ["user_id", "kind", "created_at"]
    )

    # Deferred FKs closing the users/spaces <-> media_assets cycles.
    op.create_foreign_key(
        "fk_users_avatar_asset_id_media_assets", "users", "media_assets",
        ["avatar_asset_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_spaces_cover_asset_id_media_assets", "spaces", "media_assets",
        ["cover_asset_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_spaces_cover_asset_id_media_assets", "spaces", type_="foreignkey"
    )
    op.drop_constraint("fk_users_avatar_asset_id_media_assets", "users", type_="foreignkey")
    for table in [
        "usage_records", "payments", "subscriptions", "archives", "notifications",
        "scheduled_events", "ai_generated_assets", "ai_generation_jobs", "moderation_records",
        "replies", "reactions", "contribution_attachments", "media_processing_jobs",
        "media_assets", "contributions", "invitations", "guest_access_tokens",
        "space_memberships", "space_settings", "spaces", "themes", "otp_challenges",
        "user_sessions", "users",
    ]:
        op.drop_table(table)
    for enum in ENUMS.values():
        enum.drop(op.get_bind(), checkfirst=True)
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS citext")






"""Stage III fields: AI categories, user notification prefs, consent tags.

- contributions.ai_categories: AI-assigned labels (filterable; audit trail
  stays in ai_generated_assets).
- users.digest_enabled / users.reminder_enabled: account-level toggles.
- contribution_tags: who-is-in-this-memory with consent workflow.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE tag_status AS ENUM ('pending', 'approved', 'declined')")
    op.add_column(
        "contributions",
        sa.Column("ai_categories", postgresql.ARRAY(sa.Text), nullable=False,
                  server_default="{}"),
    )
    op.add_column(
        "users",
        sa.Column("digest_enabled", sa.Boolean, nullable=False, server_default="true"),
    )
    op.add_column(
        "users",
        sa.Column("reminder_enabled", sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_table(
        "contribution_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contribution_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contributions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("suggested_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("suggested_by_token_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("guest_access_tokens.id", ondelete="SET NULL")),
        sa.Column("status", postgresql.ENUM("pending", "approved", "declined",
                                            name="tag_status", create_type=False),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_tags_contribution", "contribution_tags", ["contribution_id"])
    op.create_index("ix_tags_user_status", "contribution_tags", ["user_id", "status"])


def downgrade() -> None:
    op.drop_table("contribution_tags")
    op.drop_column("users", "reminder_enabled")
    op.drop_column("users", "digest_enabled")
    op.drop_column("contributions", "ai_categories")
    op.execute("DROP TYPE IF EXISTS tag_status")

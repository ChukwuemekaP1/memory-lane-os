"""Neon Auth linkage + audit events table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("neon_auth_sub", sa.Text, unique=True))
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("space_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("spaces.id", ondelete="CASCADE")),
        sa.Column("target_type", sa.Text),
        sa.Column("target_id", postgresql.UUID(as_uuid=True)),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_space_created", "audit_events", ["space_id", "created_at"])
    op.create_index("ix_audit_actor_created", "audit_events", ["actor_user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_column("users", "neon_auth_sub")

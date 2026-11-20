"""Spaces evolution: public visibility, kind, timezone, theme overrides.

- Adds 'public' to space_visibility (reads open, writes still credentialed).
- Adds spaces.kind (event/ongoing/personal/relationship/family/group/custom).
- Adds spaces.timezone (IANA; reminder/reveal date math runs in this zone).
- Adds spaces.theme_overrides (per-space token overrides; never touches content).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

KINDS = ("event", "ongoing", "personal", "relationship", "family", "group", "custom")


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE space_visibility ADD VALUE IF NOT EXISTS 'public'")
    op.add_column("spaces", sa.Column("kind", sa.Text, nullable=False, server_default="event"))
    op.add_column(
        "spaces", sa.Column("timezone", sa.Text, nullable=False, server_default="Africa/Lagos")
    )
    op.add_column(
        "spaces",
        sa.Column(
            "theme_overrides", sa.dialects.postgresql.JSONB, nullable=False, server_default="{}",
        ),
    )
    kinds = ", ".join(f"'{kind}'" for kind in KINDS)
    # Literal SQL: op.create_check_constraint would double-apply the ck_ prefix.
    op.execute(
        f"ALTER TABLE spaces ADD CONSTRAINT ck_spaces_kind_valid CHECK (kind IN ({kinds}))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE spaces DROP CONSTRAINT IF EXISTS ck_spaces_kind_valid")
    op.drop_column("spaces", "theme_overrides")
    op.drop_column("spaces", "timezone")
    op.drop_column("spaces", "kind")
    op.execute("UPDATE spaces SET visibility = 'link' WHERE visibility = 'public'")
    # NB: PostgreSQL has no ALTER TYPE ... DROP VALUE; the unused 'public'
    # label intentionally stays (harmless). A re-upgrade is a no-op for it
    # thanks to ADD VALUE IF NOT EXISTS.

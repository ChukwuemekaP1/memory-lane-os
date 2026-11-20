"""Phase 5/6 AI Studio production fields: image_generation, story_enhancement, token/cost tracking."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE ai_kind ADD VALUE IF NOT EXISTS 'image_generation'")
        op.execute("ALTER TYPE ai_kind ADD VALUE IF NOT EXISTS 'story_enhancement'")
        op.execute("ALTER TYPE usage_kind ADD VALUE IF NOT EXISTS 'ai_image'")
    op.add_column("ai_generation_jobs", sa.Column("input_tokens", sa.BigInteger(), nullable=True))
    op.add_column("ai_generation_jobs", sa.Column("output_tokens", sa.BigInteger(), nullable=True))
    op.add_column(
        "ai_generation_jobs",
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_generation_jobs", "cost_usd")
    op.drop_column("ai_generation_jobs", "output_tokens")
    op.drop_column("ai_generation_jobs", "input_tokens")

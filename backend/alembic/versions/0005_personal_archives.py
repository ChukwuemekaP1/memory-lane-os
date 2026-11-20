"""Personal exports: archives.space_id becomes nullable (user scope)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("archives", "space_id", existing_type=sa.dialects.postgresql.UUID(),
                    nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM archives WHERE space_id IS NULL")
    op.alter_column("archives", "space_id", existing_type=sa.dialects.postgresql.UUID(),
                    nullable=False)

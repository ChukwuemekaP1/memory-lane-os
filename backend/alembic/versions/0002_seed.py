"""Seed data: theme catalog (idempotent; safe to re-run)."""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

THEMES = [
    ("birthday-confetti", "Birthday Confetti", ["birthday"], "free",
     {"accent": "#f59e0b", "background": "#fffbeb", "font": "rounded"}),
    ("birthday-elegant", "Birthday Elegant", ["birthday", "anniversary"], "free",
     {"accent": "#7c3aed", "background": "#faf5ff", "font": "serif"}),
    ("wedding-bliss", "Wedding Bliss", ["wedding", "engagement", "anniversary"], "free",
     {"accent": "#e11d48", "background": "#fff1f2", "font": "serif"}),
    ("graduation-day", "Graduation Day", ["graduation"], "free",
     {"accent": "#1d4ed8", "background": "#eff6ff", "font": "sans"}),
    ("farewell-gold", "Farewell Gold", ["farewell"], "free",
     {"accent": "#b45309", "background": "#fffbeb", "font": "sans"}),
    ("in-loving-memory", "In Loving Memory", ["tribute"], "free",
     {"accent": "#475569", "background": "#f8fafc", "font": "serif"}),
    ("family-warmth", "Family Warmth", ["family", "baby", "travel", "community"], "free",
     {"accent": "#ea580c", "background": "#fff7ed", "font": "rounded"}),
    ("time-capsule", "Time Capsule", ["capsule", "journal"], "free",
     {"accent": "#0d9488", "background": "#f0fdfa", "font": "mono"}),
    ("celebration-premium", "Celebration Premium",
     ["birthday", "wedding", "anniversary", "graduation"], "premium",
     {"accent": "#a21caf", "background": "#fdf4ff", "font": "serif"}),
]


def upgrade() -> None:
    for slug, name, occasions, plan, tokens in THEMES:
        op.execute(
            sa.text(
                "INSERT INTO themes (id, slug, name, occasions, tokens, plan_required, is_active)"
                " VALUES (CAST(:id AS uuid), :slug, :name, CAST(:occasions AS text[]),"
                " CAST(:tokens AS jsonb), CAST(:plan AS plan), true)"
                " ON CONFLICT (slug) DO NOTHING"
            ).bindparams(
                id=str(uuid.uuid4()),
                slug=slug,
                name=name,
                occasions="{" + ",".join(occasions) + "}",
                tokens=json.dumps(tokens),
                plan=plan,
            )
        )


def downgrade() -> None:
    slugs = ", ".join(f"'{slug}'" for slug, *_ in THEMES)
    op.execute(sa.text(f"DELETE FROM themes WHERE slug IN ({slugs})"))  # noqa: S608

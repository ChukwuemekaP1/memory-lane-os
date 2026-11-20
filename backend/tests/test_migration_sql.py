"""Sync tests: Alembic offline SQL render contains the full contract.

Runs `alembic upgrade head --sql` in offline mode (no database connection)
and asserts the migration emits every table, enum, extension, and key index.
"""

import os
import subprocess
import sys
from functools import lru_cache

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TABLES = [
    "users", "user_sessions", "otp_challenges", "themes", "spaces", "space_settings",
    "space_memberships", "guest_access_tokens", "invitations", "contributions",
    "media_assets", "media_processing_jobs", "contribution_attachments", "reactions",
    "replies", "moderation_records", "ai_generation_jobs", "ai_generated_assets",
    "scheduled_events", "notifications", "archives", "subscriptions", "payments",
    "usage_records", "contribution_tags", "audit_events",
]

ENUMS = [
    "global_role", "plan", "space_visibility", "contribution_policy", "moderation_mode",
    "space_role", "guest_role_cap", "contribution_kind", "contribution_status",
    "media_kind", "media_status", "job_status", "reply_status", "moderation_target",
    "moderation_action", "ai_kind", "ai_job_status", "scheduled_kind", "scheduled_status",
    "notification_kind", "notification_status", "archive_kind", "archive_status",
    "billing_provider", "money_provider", "subscription_status", "payment_kind",
    "payment_status", "usage_kind",
]


@lru_cache(maxsize=1)
def _upgrade_sql() -> str:
    env = dict(os.environ)
    env["DATABASE_URL"] = "postgresql+asyncpg://u:p@127.0.0.1:5432/db"
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=BACKEND_ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    return completed.stdout


def test_offline_upgrade_creates_extensions():
    sql = _upgrade_sql()
    assert "CREATE EXTENSION IF NOT EXISTS citext" in sql
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in sql


def test_offline_upgrade_creates_every_enum_once():
    sql = _upgrade_sql()
    for enum in ENUMS:
        assert sql.count(f"CREATE TYPE {enum} ") == 1, enum


def test_offline_upgrade_creates_every_table():
    sql = _upgrade_sql()
    for table in TABLES:
        assert f"CREATE TABLE {table} " in sql, table


def test_offline_upgrade_key_indexes_and_constraints():
    sql = _upgrade_sql()
    for needle in [
        "ix_contributions_body_trgm",
        "uq_subscriptions_live_user",
        "uq_invitations_pending",
        "uq_payments_provider_event",
        "ix_sched_due",
        "ck_contributions_attributable",
        "ck_spaces_title_length",
        "fk_users_avatar_asset_id_media_assets",
        "fk_spaces_cover_asset_id_media_assets",
    ]:
        assert needle in sql, needle


def test_offline_upgrade_seeds_themes():
    sql = _upgrade_sql()
    assert "INSERT INTO themes" in sql
    assert "birthday-confetti" in sql
    assert "ON CONFLICT (slug) DO NOTHING" in sql


def test_offline_upgrade_spaces_evolution():
    sql = _upgrade_sql()
    assert "ADD VALUE IF NOT EXISTS 'public'" in sql
    assert "ck_spaces_kind_valid" in sql
    assert "ADD COLUMN kind" in sql
    assert "ADD COLUMN timezone" in sql
    assert "ADD COLUMN theme_overrides" in sql


def test_offline_upgrade_stage3_fields():
    sql = _upgrade_sql()
    assert "CREATE TABLE contribution_tags " in sql
    assert "CREATE TYPE tag_status " in sql
    assert "ADD COLUMN ai_categories" in sql
    assert "ADD COLUMN digest_enabled" in sql
    assert "ADD COLUMN reminder_enabled" in sql
    assert "CREATE TABLE audit_events " in sql
    assert "ADD COLUMN neon_auth_sub" in sql


def test_offline_downgrade_renders():
    env = dict(os.environ)
    env["DATABASE_URL"] = "postgresql+asyncpg://u:p@127.0.0.1:5432/db"
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0002:base", "--sql"],
        cwd=BACKEND_ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert completed.stdout.count("DROP TABLE") == 24

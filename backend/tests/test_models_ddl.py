"""Sync tests: model metadata compiles to PostgreSQL DDL (no live DB needed).

Catches model/SQL drift (bad types, FK targets, reserved names) anywhere,
including environments without a database.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

import app.models  # noqa: F401
from app.models.base import Base

EXPECTED_TABLES = {
    "users", "user_sessions", "otp_challenges", "themes", "spaces", "space_settings",
    "space_memberships", "guest_access_tokens", "invitations", "contributions",
    "media_assets", "media_processing_jobs", "contribution_attachments", "reactions",
    "replies", "moderation_records", "ai_generation_jobs", "ai_generated_assets",
    "scheduled_events", "notifications", "archives", "subscriptions", "payments",
    "usage_records", "contribution_tags", "audit_events",
}

DIALECT = postgresql.dialect()


def _ddl(table_name: str) -> str:
    table = Base.metadata.tables[table_name]
    return str(CreateTable(table).compile(dialect=DIALECT))


def test_all_tables_registered():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_every_table_compiles_to_postgres():
    for name in sorted(EXPECTED_TABLES):
        ddl = _ddl(name)
        assert f"CREATE TABLE {name}" in ddl, name


def test_key_constraints_render():
    spaces = _ddl("spaces")
    assert "ck_spaces_title_length" in spaces
    assert "ON DELETE RESTRICT" in spaces
    contrib = _ddl("contributions")
    assert "ck_contributions_attributable" in contrib
    assert "ck_contributions_no_private_letter" in contrib
    subs = _ddl("subscriptions")
    assert "uq_subscriptions_live_user" in _ddl_indexes("subscriptions")


def _ddl_indexes(table_name: str) -> str:
    from sqlalchemy.schema import CreateIndex

    table = Base.metadata.tables[table_name]
    return "\n".join(str(CreateIndex(ix).compile(dialect=DIALECT)) for ix in table.indexes)


def test_key_indexes_render():
    body_trgm = _ddl_indexes("contributions")
    assert "ix_contributions_body_trgm" in body_trgm
    assert "gin_trgm_ops" in body_trgm
    assert "uq_space_memberships_space_user" in _ddl_indexes("space_memberships")
    sched = _ddl_indexes("scheduled_events")
    assert "ix_sched_due" in sched
    assert "status = 'scheduled'" in sched


def test_enums_are_native_named_types():
    ddl = _ddl("spaces")
    assert "space_visibility" in ddl
    assert "contribution_policy" in ddl
    assert "CITEXT" in _ddl("users")
    assert "INET" in _ddl("user_sessions")
    assert "JSONB" in _ddl("themes")

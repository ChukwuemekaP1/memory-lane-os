"""Sync tests: preflight diff core + expected-schema extraction (no DB needed)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from neon_db_preflight import compare_schemas, expected_schema


def test_compare_exact_match():
    report = compare_schemas({"a", "b"}, {"a", "b", "alembic_version"}, {"e1"}, {"e1"})
    assert report["matches"] is True
    assert report["missing_tables"] == []
    assert report["extra_tables"] == []
    assert report["missing_enums"] == []


def test_compare_reports_drift():
    report = compare_schemas({"a", "b"}, {"a", "zzz"}, {"e1"}, set())
    assert report["matches"] is False
    assert report["missing_tables"] == ["b"]
    assert report["extra_tables"] == ["zzz"]
    assert report["missing_enums"] == ["e1"]


def test_expected_schema_counts():
    tables, enums = expected_schema()
    assert len(tables) == 26
    assert "audit_events" in tables and "contribution_tags" in tables
    assert len(enums) == 30
    assert "tag_status" in enums and "space_visibility" in enums

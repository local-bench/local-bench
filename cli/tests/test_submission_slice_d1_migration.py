from __future__ import annotations

import sqlite3
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = _REPO_ROOT / "web" / "migrations" / "0002_submission_slice_index.sql"

_SUBMISSIONS_COLUMNS = (
    "submission_id",
    "created_at",
    "uploaded_at",
    "origin",
    "submitter_id",
    "ticket_id",
    "status",
    "status_reason",
    "bundle_schema_version",
    "raw_bundle_sha256",
    "raw_bundle_r2_key",
    "raw_bundle_size_bytes",
    "suite_release_id",
    "suite_manifest_sha256",
    "scorecard_id",
    "model_identity_digest",
    "model_display_name",
    "lane_id",
    "tier",
    "validator_version",
    "validator_commit",
    "validated_at",
    "projection_schema_version",
    "projection_sha256",
    "projection_r2_key",
    "public_artifact_manifest_sha256",
    "public_artifact_r2_key",
    "redaction_status",
    "trust_label",
    "verification_level",
    "publish_state",
    "published_at",
    "supersedes_submission_id",
    "idempotency_key",
)

_BOARD_ENTRY_COLUMNS = (
    "entry_id",
    "submission_id",
    "board_schema_version",
    "published_at",
    "visibility",
    "origin",
    "trust_label",
    "verification_level",
    "model_display_name",
    "model_family",
    "model_file_sha256",
    "model_quant_label",
    "runtime_name",
    "runtime_version",
    "hardware_summary",
    "lane_id",
    "tier",
    "suite_release_id",
    "suite_manifest_sha256",
    "scorecard_id",
    "coverage_profile_id",
    "headline_complete",
    "headline_score",
    "partial_composite",
    "measured_headline_weight",
    "missing_headline_weight",
    "known_headline_contribution",
    "rank_scope",
    "global_rank",
    "scope_rank",
    "axis_scores_json",
    "bench_scores_json",
    "conformance_json",
    "n_scored",
    "n_errors",
    "warning_count",
    "projection_sha256",
    "bundle_sha256",
    "public_artifact_manifest_sha256",
)


def test_submission_slice_migration_applies_with_exact_index_tables() -> None:
    # Given: an empty local SQLite database standing in for D1.
    connection = sqlite3.connect(":memory:")

    # When: the Batch 2a migration is applied.
    connection.executescript(_MIGRATION.read_text(encoding="utf-8"))

    # Then: D1 has only the requested index/pointer columns for the new tables.
    assert _columns(connection, "submissions") == _SUBMISSIONS_COLUMNS
    assert _columns(connection, "board_entries") == _BOARD_ENTRY_COLUMNS
    assert _has_unique_index(connection, "submissions", "idempotency_key")
    assert "verification_events" not in _tables(connection)


def _columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    rows = connection.execute(f"pragma table_info({table})").fetchall()
    return tuple(str(row[1]) for row in rows)


def _tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("select name from sqlite_master where type = 'table'").fetchall()
    return {str(row[0]) for row in rows}


def _has_unique_index(connection: sqlite3.Connection, table: str, column: str) -> bool:
    for index in connection.execute(f"pragma index_list({table})").fetchall():
        if int(index[2]) != 1:
            continue
        indexed = connection.execute(f"pragma index_info({index[1]})").fetchall()
        if tuple(str(row[2]) for row in indexed) == (column,):
            return True
    return False

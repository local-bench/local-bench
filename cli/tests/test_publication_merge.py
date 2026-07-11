from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "web"))

from publication_export import PublicationExportError, canonical_bytes  # noqa: E402
from publication_merge import (  # noqa: E402
    assert_protected_tree_unchanged,
    merge_publication_bundle,
    protected_tree,
)


def test_two_artifact_variants_merge_to_one_isolated_unranked_group(tmp_path: Path) -> None:
    bundle, out, catalog, board = _fixture(tmp_path)
    before = protected_tree(out)

    record = merge_publication_bundle(bundle, out, catalog_path=catalog, board_path=board)
    assert_protected_tree_unchanged(before, out)

    group = json.loads((out / "community" / "groups" / f"{'1' * 32}.json").read_text())
    assert group["identity_label"] == "community-declared, identity-unverified"
    assert group["ranked"] is False
    assert len(group["variants"]) == 2
    assert {variant["artifact_sha256"] for variant in group["variants"]} == {"a" * 64, "b" * 64}
    assert record["build_input_manifest"]["snapshot_id"] == "pub_test"
    assert len(record["build_input_manifest_digest"]) == 64
    assert len(record["output_tree_digest"]) == 64


def test_preview_rows_are_excluded_from_production_and_present_only_in_preview(tmp_path: Path) -> None:
    bundle, production, catalog, board = _fixture(tmp_path)
    snapshot_path = bundle / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text())
    snapshot["rows"][0]["publish_state"] = "preview"
    snapshot["snapshot_digest"] = hashlib.sha256(canonical_bytes(snapshot["rows"])).hexdigest()
    snapshot_path.write_bytes(canonical_bytes(snapshot))

    merge_publication_bundle(bundle, production, catalog_path=catalog, board_path=board, surface="production")
    production_group = json.loads((production / "community" / "groups" / f"{'1' * 32}.json").read_text())
    assert [row["submission_id"] for row in production_group["variants"]] == ["sub_2"]

    preview = tmp_path / "preview"
    merge_publication_bundle(bundle, preview, catalog_path=catalog, board_path=board, surface="previewDeploy")
    preview_group = json.loads((preview / "community" / "groups" / f"{'1' * 32}.json").read_text())
    assert [row["submission_id"] for row in preview_group["variants"]] == ["sub_1", "sub_2"]


def test_snapshot_truncation_and_catalog_collision_fail_closed(tmp_path: Path) -> None:
    bundle, out, catalog, board = _fixture(tmp_path)
    snapshot_path = bundle / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text())
    snapshot["total_count"] = 3
    snapshot_path.write_bytes(canonical_bytes(snapshot))
    with pytest.raises(PublicationExportError, match="truncation"):
        merge_publication_bundle(bundle, out, catalog_path=catalog, board_path=board)

    bundle, out, catalog, board = _fixture(tmp_path / "collision", catalog_id=f"community-group:{'1' * 32}")
    with pytest.raises(PublicationExportError, match="collision"):
        merge_publication_bundle(bundle, out, catalog_path=catalog, board_path=board)


def test_full_protected_payload_guard_detects_any_mutation(tmp_path: Path) -> None:
    _bundle, out, _catalog, _board = _fixture(tmp_path)
    before = protected_tree(out)
    (out / "models" / "protected.json").write_text('{"mutated":true}', encoding="utf-8")
    with pytest.raises(PublicationExportError, match="protected payload changed"):
        assert_protected_tree_unchanged(before, out)


def test_same_complete_manifest_reproduces_the_same_output_tree_digest(tmp_path: Path) -> None:
    bundle, out, catalog, board = _fixture(tmp_path)
    source = tmp_path / "source-run.json"
    source.write_text('{"input":"bytes"}', encoding="utf-8")
    first = merge_publication_bundle(
        bundle, out, catalog_path=catalog, board_path=board, source_run_paths=[source],
    )
    second = merge_publication_bundle(
        bundle, out, catalog_path=catalog, board_path=board, source_run_paths=[source],
    )
    assert first["build_input_manifest"] == second["build_input_manifest"]
    assert first["output_tree_digest"] == second["output_tree_digest"]
    assert first["build_input_manifest"]["source_run_byte_digests"] == [{
        "path": "source-run.json",
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }]


def _fixture(tmp_path: Path, *, catalog_id: str = "catalog/protected") -> tuple[Path, Path, Path, Path]:
    bundle = tmp_path / "bundle"
    projections = bundle / "projections"
    projections.mkdir(parents=True)
    out = tmp_path / "out"
    (out / "models").mkdir(parents=True)
    (out / "models" / "protected.json").write_text('{"slug":"protected"}', encoding="utf-8")
    (out / "index.json").write_text('{"models":[{"catalog_id":"catalog/protected","ranked":true,"slug":"protected"}]}', encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"models": [{"id": catalog_id, "slug": "protected"}]}), encoding="utf-8")
    board = tmp_path / "board.json"
    board.write_text('{"models":[]}', encoding="utf-8")
    rows = []
    for index, artifact in enumerate(("a" * 64, "b" * 64), 1):
        projection = {
            "schema_version": "localbench.accepted_result_projection.v2", "origin": "community",
            "model": {"display_name": f"Variant {index}", "file_sha256": artifact},
            "scores": {"partial_composite": index / 10},
        }
        payload = canonical_bytes(projection)
        digest = hashlib.sha256(payload).hexdigest()
        (projections / f"{digest}.json").write_bytes(payload)
        rows.append({
            "community_model_group_id": f"community-group:{'1' * 32}", "decision_class": "publishable",
            "ordinal": index, "projection_object_sha256": digest, "projection_r2_key": f"projections/sha256/{digest}.json",
            "publish_state": "published", "state_revision": 1, "submission_id": f"sub_{index}",
            "suite_manifest_sha256": "c" * 64, "suite_release_id": "suite", "trust_class": "verifier",
        })
    snapshot = {
        "created_at": "2026-07-12T00:00:00Z", "publication_revision": 2,
        "snapshot_digest": hashlib.sha256(canonical_bytes(rows)).hexdigest(), "snapshot_id": "pub_test",
        "total_count": len(rows), "rows": rows,
    }
    (bundle / "snapshot.json").write_bytes(canonical_bytes(snapshot))
    return bundle, out, catalog, board

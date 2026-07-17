from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

from publication_merge_fixture import (
    GROUP_ONE,
    GROUP_TWO,
    expect_publication_error as _expect_publication_error,
    fixture as _fixture,
    merge as _merge,
    overlay_entry as _overlay_entry,
    publication_merge,
)
from publication_export import PublicationExportError, canonical_bytes  # noqa: E402


def invalid_group_parent(root: Path) -> None:
    bundle, out, catalog, board, overlay, _rows = _fixture(
        root, group_ids=("community-group:../../x",),
    )
    _expect_publication_error(
        lambda: _merge(bundle, out, catalog, board, overlay),
        "community model group id",
    )
    assert not (out / "x.json").exists()


def invalid_group_nonhex(root: Path) -> None:
    bundle, out, catalog, board, overlay, _rows = _fixture(
        root, group_ids=(f"community-group:{'Z' * 32}",),
    )
    _expect_publication_error(
        lambda: _merge(bundle, out, catalog, board, overlay),
        "community model group id",
    )


def bad_digest(root: Path) -> None:
    bundle, out, catalog, board, overlay, rows = _fixture(root / "projection")
    rows[0]["projection_object_sha256"] = "g" * 64
    snapshot_path = bundle / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["rows"] = rows
    snapshot["snapshot_digest"] = hashlib.sha256(canonical_bytes(rows)).hexdigest()
    snapshot_path.write_bytes(canonical_bytes(snapshot))
    _expect_publication_error(
        lambda: _merge(bundle, out, catalog, board, overlay),
        "projection object sha256",
    )

    bundle, out, catalog, board, overlay, _rows = _fixture(
        root / "artifact", artifact_override="A" * 64,
    )
    _expect_publication_error(
        lambda: _merge(bundle, out, catalog, board, overlay),
        "artifact sha256",
    )


def stale_group(root: Path) -> None:
    bundle, out, catalog, board, overlay, _rows = _fixture(
        root, group_ids=(GROUP_ONE, GROUP_TWO),
    )
    _merge(bundle, out, catalog, board, overlay)
    stale = out / "community" / "groups" / f"{'2' * 32}.json"
    assert stale.is_file()
    _merge(bundle, out, catalog, board, overlay, suppressed=("sub_2",))
    assert not stale.exists()


def overlay_left_join(root: Path) -> None:
    bundle, out, catalog, board, overlay, _rows = _fixture(root)
    matched = "a" * 64
    unmatched = "f" * 64
    overlay.write_bytes(canonical_bytes({
        "entries": {
            matched: _overlay_entry(matched),
            unmatched: _overlay_entry(unmatched, "unused/model"),
        },
        "schema_version": "localbench.community_lineage_overlay.v1",
    }))
    _merge(bundle, out, catalog, board, overlay)
    group_bytes = (out / "community" / "groups" / f"{'1' * 32}.json").read_bytes()
    group = json.loads(group_bytes)
    assert group["variants"][0]["lineage_enrichment"]["repo"]["id"] == "owner/model"
    assert unmatched.encode() not in group_bytes
    assert b"unused/model" not in group_bytes


def overlay_digest(root: Path) -> None:
    bundle, out, catalog, board, overlay, _rows = _fixture(root)
    record = _merge(bundle, out, catalog, board, overlay)
    assert record["build_input_manifest"]["lineage_overlay_bytes_digest"] == hashlib.sha256(
        overlay.read_bytes(),
    ).hexdigest()


def score_shape(root: Path) -> None:
    invalid_scores = (
        {"partial_composite": 0.5, "unknown": 0.1},
        {"partial_composite": 1.01},
        {"partial_composite": float("nan")},
        {"measured_headline_weight": -0.1, "partial_composite": 0.5},
        {"n": -1, "partial_composite": 0.5},
        {"n": True, "partial_composite": 0.5},
    )
    for index, scores in enumerate(invalid_scores):
        bundle, out, catalog, board, overlay, _rows = _fixture(
            root / str(index), scores=scores,
        )
        _expect_publication_error(
            lambda: _merge(bundle, out, catalog, board, overlay),
            "projection.scores",
        )


def atomic_validation(root: Path) -> None:
    bundle, out, catalog, board, overlay, _rows = _fixture(root)
    community = out / "community"
    community.mkdir()
    prior_index = b'{"prior":true}'
    (community / "index.json").write_bytes(prior_index)

    def reject_staged_tree(_community_dir: Path) -> None:
        raise PublicationExportError("staged community validation failed")

    publication_merge._validate_community_tree = reject_staged_tree
    _expect_publication_error(
        lambda: _merge(bundle, out, catalog, board, overlay),
        "staged community validation failed",
    )
    assert (community / "index.json").read_bytes() == prior_index
    assert sorted(path.name for path in out.iterdir() if "community-" in path.name) == []


CASES: dict[str, Callable[[Path], None]] = {
    "atomic_validation": atomic_validation,
    "bad_digest": bad_digest,
    "invalid_group_nonhex": invalid_group_nonhex,
    "invalid_group_parent": invalid_group_parent,
    "overlay_digest": overlay_digest,
    "overlay_left_join": overlay_left_join,
    "score_shape": score_shape,
    "stale_group": stale_group,
}


def main() -> None:
    case_name = sys.argv[1]
    with TemporaryDirectory(prefix="publication-merge-case-") as temp_dir:
        CASES[case_name](Path(temp_dir))


if __name__ == "__main__":
    main()

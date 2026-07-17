from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Callable

WEB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WEB_ROOT))

import publication_merge  # noqa: E402
from publication_export import PublicationExportError, canonical_bytes  # noqa: E402

GROUP_ONE = f"community-group:{'1' * 32}"
GROUP_TWO = f"community-group:{'2' * 32}"


def overlay_entry(artifact: str, repo_id: str = "owner/model") -> dict[str, Any]:
    return {
        "artifact_sha256": artifact,
        "association": {
            "artifact_to_repo": "unverified",
            "basis": "maintainer-associated",
            "note": "Maintainer association only",
        },
        "card_declared_edges": [{
            "base": "base/model",
            "base_revision": "b" * 40,
            "child": repo_id,
            "child_revision": "a" * 40,
            "source": "hf-model-card",
        }],
        "repo": {"id": repo_id, "revision": "a" * 40},
        "resolution": {"resolved_at": "2026-07-18T01:30:00Z", "status": "complete"},
    }


def fixture(
    root: Path,
    *,
    group_ids: tuple[str, ...] = (GROUP_ONE,),
    scores: dict[str, Any] | None = None,
    artifact_override: str | None = None,
) -> tuple[Path, Path, Path, Path, Path, list[dict[str, Any]]]:
    bundle = root / "bundle"
    projections = bundle / "projections"
    projections.mkdir(parents=True)
    out = root / "out"
    (out / "models").mkdir(parents=True)
    (out / "models" / "protected.json").write_text('{"slug":"protected"}', encoding="utf-8")
    (out / "index.json").write_text('{"models":[]}', encoding="utf-8")
    catalog = root / "catalog.json"
    catalog.write_text('{"models":[]}', encoding="utf-8")
    board = root / "board.json"
    board.write_text('{"models":[]}', encoding="utf-8")
    overlay = root / "overlay.json"
    overlay.write_bytes(canonical_bytes({
        "entries": {},
        "schema_version": "localbench.community_lineage_overlay.v1",
    }))
    rows: list[dict[str, Any]] = []
    for index, group_id in enumerate(group_ids, 1):
        artifact = artifact_override or f"{index + 9:x}" * 64
        projection = {
            "model": {
                "display_name": f"Variant {index}",
                "file_sha256": artifact,
                "quant_label": "Q4_K_M",
            },
            "origin": "community",
            "schema_version": "localbench.accepted_result_projection.v2",
            "scores": scores or {
                "measured_headline_weight": 0.75,
                "missing_headline_weight": 0.25,
                "partial_composite": 0.5,
            },
        }
        has_nonfinite_score = any(
            isinstance(value, float) and not math.isfinite(value)
            for value in projection["scores"].values()
        )
        payload = (
            json.dumps(projection, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            if has_nonfinite_score
            else canonical_bytes(projection)
        )
        digest = hashlib.sha256(payload).hexdigest()
        (projections / f"{digest}.json").write_bytes(payload)
        rows.append({
            "community_model_group_id": group_id,
            "projection_object_sha256": digest,
            "publish_state": "published",
            "submission_id": f"sub_{index}",
        })
    control = {
        "active_snapshot_id": "pub_test",
        "edge_block_revision": 0,
        "publication_revision": 2,
        "suppressed_submission_ids": [],
    }
    snapshot = {
        "activated_at": "2026-07-18T00:01:00Z",
        "created_at": "2026-07-18T00:00:00Z",
        "publication_control": control,
        "publication_revision": 2,
        "rows": rows,
        "snapshot_digest": hashlib.sha256(canonical_bytes(rows)).hexdigest(),
        "snapshot_id": "pub_test",
        "total_count": len(rows),
    }
    (bundle / "snapshot.json").write_bytes(canonical_bytes(snapshot))
    return bundle, out, catalog, board, overlay, rows


def merge(
    bundle: Path,
    out: Path,
    catalog: Path,
    board: Path,
    overlay: Path,
    *,
    suppressed: tuple[str, ...] = (),
) -> dict[str, Any]:
    publication_merge.fetch_live_publication_control = lambda *_args: {
        "active_snapshot_id": "pub_test",
        "edge_block_revision": 0,
        "publication_revision": 2,
        "suppressed_submission_ids": list(suppressed),
    }
    return publication_merge.merge_publication_bundle(
        bundle,
        out,
        catalog_path=catalog,
        board_path=board,
        lineage_overlay_path=overlay,
        publication_admin_secret="secret",
        publication_base_url="https://publication.invalid",
    )


def expect_publication_error(action: Callable[[], Any], message: str) -> None:
    try:
        action()
    except PublicationExportError as error:
        if message not in str(error):
            raise AssertionError(f"expected {message!r} in {str(error)!r}") from error
    else:
        raise AssertionError("expected PublicationExportError")

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

from publication_export import PublicationExportError, canonical_bytes, fetch_live_publication_control
from publication_materialization import (
    publication_tree_digest as _publication_tree_digest,
    replace_community_tree as _replace_community_tree,
)
from publication_validation import (
    IDENTITY_LABEL,
    LINEAGE_OVERLAY_PATH,
    SCHEMA_VERSION,
    group_id_text as _group_id,
    lineage_overlay as _lineage_overlay,
    scores as _scores,
    sha256 as _sha256,
    validate_community_tree as _validate_community_tree,
)

MAPPER_VERSION = "community-projection-mapper-v2"
SURFACE_POLICY_PATH = Path(__file__).with_name("publication-surface-policy.json")


def merge_publication_bundle(
    bundle_dir: Path,
    out_dir: Path,
    *,
    catalog_path: Path,
    board_path: Path,
    surface: str = "production",
    source_run_paths: Iterable[Path] = (),
    build_parameters: dict[str, Any] | None = None,
    lineage_overlay_path: Path | None = None,
    publication_base_url: str | None = None,
    publication_admin_secret: str | None = None,
) -> dict[str, Any]:
    snapshot = _object(json.loads((bundle_dir / "snapshot.json").read_text(encoding="utf-8")), "snapshot")
    rows = _objects(snapshot.get("rows"), "snapshot.rows")
    if len(rows) != _integer(snapshot.get("total_count"), "snapshot.total_count"):
        raise PublicationExportError("snapshot truncation: row count mismatch")
    if _digest(canonical_bytes(rows)) != _text(snapshot, "snapshot_digest"):
        raise PublicationExportError("snapshot digest mismatch")
    control = _object(snapshot.get("publication_control"), "snapshot.publication_control")
    snapshot_id = _text(snapshot, "snapshot_id")
    if control.get("active_snapshot_id") != snapshot_id:
        raise PublicationExportError("bundle snapshot is not the active snapshot")
    if control.get("publication_revision") != snapshot.get("publication_revision"):
        raise PublicationExportError("active publication revision mismatch")
    if not isinstance(snapshot.get("activated_at"), str) or not snapshot["activated_at"]:
        raise PublicationExportError("active snapshot is not completed and activated")
    if not publication_base_url or not publication_admin_secret:
        raise PublicationExportError("live publication base URL and admin secret are required at build time")
    live_control = fetch_live_publication_control(publication_base_url, publication_admin_secret, snapshot_id)
    if live_control.get("active_snapshot_id") != snapshot_id:
        raise PublicationExportError("bundle snapshot is not the live active snapshot")
    if live_control.get("publication_revision") != snapshot.get("publication_revision"):
        raise PublicationExportError("bundle revision does not match the live publication revision")
    captured_suppressed = control.get("suppressed_submission_ids")
    live_suppressed = live_control.get("suppressed_submission_ids")
    if not isinstance(captured_suppressed, list) or not all(isinstance(item, str) for item in captured_suppressed):
        raise PublicationExportError("suppression set is missing or malformed")
    if not isinstance(live_suppressed, list) or not all(isinstance(item, str) for item in live_suppressed):
        raise PublicationExportError("live suppression set is missing or malformed")
    suppressed_ids = set(captured_suppressed) | set(live_suppressed)
    rows = [row for row in rows if _text(row, "submission_id") not in suppressed_ids]
    surface_policy = _object(json.loads(SURFACE_POLICY_PATH.read_text(encoding="utf-8")), "publication surface policy")
    if surface not in {"production", "previewDeploy"}:
        raise PublicationExportError(f"unknown publication surface: {surface}")
    rows = [row for row in rows if _surface_enabled(surface_policy, row, surface)]
    overlay_path = lineage_overlay_path or LINEAGE_OVERLAY_PATH
    overlay_bytes = overlay_path.read_bytes()
    lineage_by_artifact = _lineage_overlay(json.loads(overlay_bytes))
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog_ids = _catalog_identities(catalog)
    groups: dict[str, list[dict[str, Any]]] = {}
    projections: dict[str, dict[str, Any]] = {}
    for row in rows:
        group_id = _group_id(_text(row, "community_model_group_id"))
        if group_id in catalog_ids:
            raise PublicationExportError("catalog/group-id collision")
        digest = _sha256(_text(row, "projection_object_sha256"), "projection object sha256")
        payload = (bundle_dir / "projections" / f"{digest}.json").read_bytes()
        if _digest(payload) != digest:
            raise PublicationExportError("projection object digest mismatch")
        projection = _object(json.loads(payload), "projection")
        if projection.get("origin") != "community":
            raise PublicationExportError("community snapshot contains a trusted projection")
        projections[digest] = projection
        groups.setdefault(group_id, []).append(row)
    out_dir.mkdir(parents=True, exist_ok=True)
    community_dir = out_dir / "community"
    staged_community = Path(tempfile.mkdtemp(prefix=".community-stage-", dir=out_dir))
    try:
        groups_dir = staged_community / "groups"
        groups_dir.mkdir()
        index_groups: list[dict[str, Any]] = []
        for group_id, group_rows in sorted(groups.items()):
            suffix = group_id.removeprefix("community-group:")
            artifacts: set[str] = set()
            variants: list[dict[str, Any]] = []
            for row in sorted(group_rows, key=lambda value: _text(value, "submission_id")):
                projection_digest = _sha256(
                    _text(row, "projection_object_sha256"), "projection object sha256",
                )
                projection = projections[projection_digest]
                model = _object(projection.get("model"), "projection.model")
                artifact = _sha256(_text(model, "file_sha256"), "artifact sha256")
                if artifact in artifacts:
                    raise PublicationExportError("duplicate artifact variant in community group")
                artifacts.add(artifact)
                variant = {
                    "artifact_sha256": artifact,
                    "display_name": model.get("display_name"),
                    "projection_object_sha256": projection_digest,
                    "quant_label": model.get("quant_label"),
                    "ranked": False,
                    "scores": _scores(projection.get("scores")),
                    "submission_id": _text(row, "submission_id"),
                }
                lineage = lineage_by_artifact.get(artifact)
                if lineage is not None:
                    variant["lineage_enrichment"] = lineage
                variants.append(variant)
            group_payload = {
                "community_model_group_id": group_id,
                "identity_label": IDENTITY_LABEL,
                "ranked": False,
                "schema_version": SCHEMA_VERSION,
                "variants": variants,
            }
            (groups_dir / f"{suffix}.json").write_bytes(canonical_bytes(group_payload))
            index_groups.append({
                "community_model_group_id": group_id,
                "group_path": f"community/groups/{suffix}.json",
                "n_variants": len(variants),
            })
        (staged_community / "index.json").write_bytes(canonical_bytes({
            "groups": index_groups,
            "schema_version": SCHEMA_VERSION,
        }))
        manifest = {
            "builder_commit": _builder_commit(),
            "build_parameters": build_parameters or {},
            "catalog_bytes_digest": _digest(catalog_path.read_bytes()),
            "frozen_generation_time": snapshot.get("created_at"),
            "lineage_overlay_bytes_digest": _digest(overlay_bytes),
            "mapper_version": MAPPER_VERSION,
            "projection_object_sha256s": sorted(projections),
            "protected_board_bytes_digest": _digest(board_path.read_bytes()),
            "publication_control": live_control,
            "schema_version": SCHEMA_VERSION,
            "source_run_byte_digests": _file_digest_entries(source_run_paths),
            "snapshot_digest": snapshot.get("snapshot_digest"),
            "snapshot_id": snapshot.get("snapshot_id"),
            "surface": surface,
            "surface_policy_bytes_digest": _digest(SURFACE_POLICY_PATH.read_bytes()),
        }
        manifest_digest = _digest(canonical_bytes(manifest))
        output_tree_digest = _publication_tree_digest(out_dir, staged_community)
        record = {
            "build_input_manifest": manifest,
            "build_input_manifest_digest": manifest_digest,
            "output_tree_digest": output_tree_digest,
        }
        (staged_community / "publication-build.json").write_bytes(canonical_bytes(record))
        _validate_community_tree(staged_community)
        _replace_community_tree(staged_community, community_dir)
        return record
    finally:
        if staged_community.exists():
            shutil.rmtree(staged_community)


def _file_digest_entries(paths: Iterable[Path]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for path in sorted({item.resolve() for item in paths if item.is_file()}, key=lambda item: item.as_posix()):
        try:
            label = path.relative_to(Path(__file__).resolve().parents[1]).as_posix()
        except ValueError:
            label = path.name
        entries.append({"path": label, "sha256": _digest(path.read_bytes())})
    return entries


def _surface_enabled(policy: dict[str, Any], row: dict[str, Any], surface: str) -> bool:
    publish_state = _text(row, "publish_state")
    state_policy = _object(policy.get(publish_state), f"publication surface policy.{publish_state}")
    enabled = state_policy.get(surface)
    if not isinstance(enabled, bool):
        raise PublicationExportError(f"publication surface policy.{publish_state}.{surface} must be a boolean")
    return enabled


def protected_tree(out_dir: Path) -> dict[str, bytes]:
    files = {str(path.relative_to(out_dir)).replace("\\", "/"): path.read_bytes() for path in out_dir.rglob("*") if path.is_file() and "community" not in path.relative_to(out_dir).parts}
    index = _object(json.loads(files.get("index.json", b"{}").decode("utf-8")), "index")
    models = _objects(index.get("models", []), "index.models")
    files["@ranked-reference-population"] = canonical_bytes([model for model in models if model.get("ranked") is True])
    files["@catalog-mappings"] = canonical_bytes(sorted((model.get("slug"), model.get("catalog_id")) for model in models))
    files["@protected-route-paths"] = canonical_bytes(sorted(files))
    return files


def assert_protected_tree_unchanged(before: dict[str, bytes], out_dir: Path) -> None:
    after = protected_tree(out_dir)
    if before != after:
        changed = sorted(set(before) ^ set(after) | {key for key in set(before) & set(after) if before[key] != after[key]})
        raise PublicationExportError(f"protected payload changed during community merge: {changed}")


def _catalog_identities(value: Any) -> set[str]:
    items = value if isinstance(value, list) else _object(value, "catalog").get("models", [])
    return {identity for item in _objects(items, "catalog.models") for identity in (item.get("id"), item.get("slug")) if isinstance(identity, str)}


def _builder_commit() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PublicationExportError(f"{label} must be an object")
    return value


def _objects(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise PublicationExportError(f"{label} must be objects")
    return list(value)


def _text(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise PublicationExportError(f"{key} must be a string")
    return item


def _integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise PublicationExportError(f"{label} must be an integer")
    return value

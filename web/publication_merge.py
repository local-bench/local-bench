from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from publication_export import PublicationExportError, canonical_bytes

IDENTITY_LABEL = "community-declared, identity-unverified"
MAPPER_VERSION = "community-projection-mapper-v1"
SCHEMA_VERSION = "localbench.community_publication.v1"
SURFACE_POLICY_PATH = Path(__file__).with_name("publication-surface-policy.json")


def merge_publication_bundle(
    bundle_dir: Path,
    out_dir: Path,
    *,
    catalog_path: Path,
    board_path: Path,
    surface: str = "production",
) -> dict[str, Any]:
    snapshot = _object(json.loads((bundle_dir / "snapshot.json").read_text(encoding="utf-8")), "snapshot")
    rows = _objects(snapshot.get("rows"), "snapshot.rows")
    if len(rows) != _integer(snapshot.get("total_count"), "snapshot.total_count"):
        raise PublicationExportError("snapshot truncation: row count mismatch")
    if _digest(canonical_bytes(rows)) != _text(snapshot, "snapshot_digest"):
        raise PublicationExportError("snapshot digest mismatch")
    surface_policy = _object(json.loads(SURFACE_POLICY_PATH.read_text(encoding="utf-8")), "publication surface policy")
    if surface not in {"production", "previewDeploy"}:
        raise PublicationExportError(f"unknown publication surface: {surface}")
    rows = [row for row in rows if _surface_enabled(surface_policy, row, surface)]
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog_ids = _catalog_identities(catalog)
    groups: dict[str, list[dict[str, Any]]] = {}
    projections: dict[str, dict[str, Any]] = {}
    for row in rows:
        group_id = _text(row, "community_model_group_id")
        if not group_id.startswith("community-group:") or group_id in catalog_ids:
            raise PublicationExportError("catalog/group-id collision")
        digest = _text(row, "projection_object_sha256")
        payload = (bundle_dir / "projections" / f"{digest}.json").read_bytes()
        if _digest(payload) != digest:
            raise PublicationExportError("projection object digest mismatch")
        projection = _object(json.loads(payload), "projection")
        if projection.get("origin") != "community":
            raise PublicationExportError("community snapshot contains a trusted projection")
        projections[digest] = projection
        groups.setdefault(group_id, []).append(row)
    community_dir = out_dir / "community"
    groups_dir = community_dir / "groups"
    groups_dir.mkdir(parents=True, exist_ok=True)
    index_groups: list[dict[str, Any]] = []
    for group_id, group_rows in sorted(groups.items()):
        suffix = group_id.removeprefix("community-group:")
        artifacts: set[str] = set()
        variants: list[dict[str, Any]] = []
        for row in sorted(group_rows, key=lambda value: _text(value, "submission_id")):
            projection = projections[_text(row, "projection_object_sha256")]
            model = _object(projection.get("model"), "projection.model")
            artifact = _text(model, "file_sha256")
            if artifact in artifacts:
                raise PublicationExportError("duplicate artifact variant in community group")
            artifacts.add(artifact)
            variants.append({
                "artifact_sha256": artifact,
                "display_name": model.get("display_name"),
                "projection_object_sha256": _text(row, "projection_object_sha256"),
                "ranked": False,
                "scores": projection.get("scores"),
                "submission_id": _text(row, "submission_id"),
            })
        payload = {"community_model_group_id": group_id, "identity_label": IDENTITY_LABEL, "ranked": False, "schema_version": SCHEMA_VERSION, "variants": variants}
        (groups_dir / f"{suffix}.json").write_bytes(canonical_bytes(payload))
        index_groups.append({"community_model_group_id": group_id, "group_path": f"community/groups/{suffix}.json", "n_variants": len(variants)})
    (community_dir / "index.json").write_bytes(canonical_bytes({"groups": index_groups, "schema_version": SCHEMA_VERSION}))
    manifest = {
        "builder_commit": _builder_commit(),
        "catalog_bytes_digest": _digest(catalog_path.read_bytes()),
        "frozen_generation_time": snapshot.get("created_at"),
        "mapper_version": MAPPER_VERSION,
        "projection_object_sha256s": sorted(projections),
        "protected_board_bytes_digest": _digest(board_path.read_bytes()),
        "schema_version": SCHEMA_VERSION,
        "snapshot_digest": snapshot.get("snapshot_digest"),
        "snapshot_id": snapshot.get("snapshot_id"),
    }
    manifest_digest = _digest(canonical_bytes(manifest))
    output_tree_digest = _tree_digest(out_dir, exclude={"community/publication-build.json"})
    record = {"build_input_manifest": manifest, "build_input_manifest_digest": manifest_digest, "output_tree_digest": output_tree_digest}
    (community_dir / "publication-build.json").write_bytes(canonical_bytes(record))
    return record


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


def _tree_digest(root: Path, *, exclude: set[str]) -> str:
    entries = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = str(path.relative_to(root)).replace("\\", "/")
        if relative not in exclude:
            entries.append({"path": relative, "sha256": _digest(path.read_bytes())})
    return _digest(canonical_bytes(entries))


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

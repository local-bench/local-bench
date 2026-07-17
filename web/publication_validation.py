from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from publication_export import PublicationExportError

IDENTITY_LABEL = "community-declared, identity-unverified"
SCHEMA_VERSION = "localbench.community_publication.v2"
LINEAGE_OVERLAY_PATH = Path(__file__).with_name("community_lineage_overlay.json")
GROUP_ID_RE = re.compile(r"community-group:[0-9a-f]{32}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
REVISION_RE = re.compile(r"[0-9a-f]{40}")
REPO_ID_RE = re.compile(r"[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+")
UTC_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z")
SCORE_KEYS = {
    "composite_full", "composite_static", "headline_score", "known_headline_contribution",
    "measured_headline_weight", "missing_headline_weight", "n", "partial_composite",
    "partial_composite_scope", "rank_scope", "static_index_version",
}
NULLABLE_SCORE_KEYS = {"composite_full", "composite_static", "headline_score"}
BOUNDED_SCORE_KEYS = {
    "composite_full", "composite_static", "headline_score", "known_headline_contribution",
    "measured_headline_weight", "missing_headline_weight", "partial_composite",
}


def lineage_overlay(value: Any) -> dict[str, dict[str, Any]]:
    overlay = _object(value, "lineage overlay")
    _exact_keys(overlay, {"entries", "schema_version"}, "lineage overlay")
    if overlay.get("schema_version") != "localbench.community_lineage_overlay.v1":
        raise PublicationExportError("lineage overlay schema version is unsupported")
    entries = _object(overlay.get("entries"), "lineage overlay.entries")
    parsed: dict[str, dict[str, Any]] = {}
    for artifact, value_entry in entries.items():
        artifact_sha256 = sha256(artifact, "lineage overlay artifact sha256")
        parsed[artifact_sha256] = _lineage_entry(value_entry, artifact_sha256)
    return parsed


def _lineage_entry(value: Any, artifact_sha256: str) -> dict[str, Any]:
    entry = _object(value, f"lineage overlay.entries.{artifact_sha256}")
    _exact_keys(
        entry,
        {"artifact_sha256", "association", "card_declared_edges", "repo", "resolution"},
        "lineage overlay entry",
    )
    if sha256(_text(entry, "artifact_sha256"), "lineage overlay artifact sha256") != artifact_sha256:
        raise PublicationExportError("lineage overlay artifact sha256 must equal its entry key")
    association = _object(entry.get("association"), "lineage overlay association")
    _exact_keys(association, {"artifact_to_repo", "basis", "note"}, "lineage overlay association")
    if association.get("basis") != "maintainer-associated":
        raise PublicationExportError("lineage overlay association basis is unsupported")
    if association.get("artifact_to_repo") != "unverified":
        raise PublicationExportError("lineage overlay artifact-to-repo status is unsupported")
    if len(_text(association, "note")) > 200:
        raise PublicationExportError("lineage overlay association note exceeds 200 characters")
    repo = _object(entry.get("repo"), "lineage overlay repo")
    _exact_keys(repo, {"id", "revision"}, "lineage overlay repo")
    _repo_id(_text(repo, "id"), "lineage overlay repo id")
    _revision(_text(repo, "revision"), "lineage overlay repo revision")
    edges = _objects(entry.get("card_declared_edges"), "lineage overlay card_declared_edges")
    for edge in edges:
        _exact_keys(
            edge,
            {"base", "base_revision", "child", "child_revision", "source"},
            "lineage overlay card-declared edge",
        )
        _repo_id(_text(edge, "child"), "lineage overlay edge child")
        _revision(_text(edge, "child_revision"), "lineage overlay edge child revision")
        _repo_id(_text(edge, "base"), "lineage overlay edge base")
        base_revision = edge.get("base_revision")
        if base_revision is not None:
            if not isinstance(base_revision, str):
                raise PublicationExportError("lineage overlay edge base revision must be a string or null")
            _revision(base_revision, "lineage overlay edge base revision")
        if edge.get("source") != "hf-model-card":
            raise PublicationExportError("lineage overlay edge source is unsupported")
    resolution = _object(entry.get("resolution"), "lineage overlay resolution")
    _exact_keys(resolution, {"resolved_at", "status"}, "lineage overlay resolution")
    resolved_at = _text(resolution, "resolved_at")
    if UTC_TIMESTAMP_RE.fullmatch(resolved_at) is None:
        raise PublicationExportError("lineage overlay resolved_at must be an ISO8601 UTC timestamp")
    try:
        datetime.fromisoformat(resolved_at.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise PublicationExportError("lineage overlay resolved_at must be an ISO8601 UTC timestamp") from error
    if resolution.get("status") not in {"complete", "truncated", "partial"}:
        raise PublicationExportError("lineage overlay resolution status is unsupported")
    return entry


def scores(value: Any) -> dict[str, Any]:
    parsed = _object(value, "projection.scores")
    unknown = set(parsed) - SCORE_KEYS
    if unknown:
        raise PublicationExportError(f"projection.scores contains unknown keys: {sorted(unknown)}")
    for key, item in parsed.items():
        if key in BOUNDED_SCORE_KEYS:
            if item is None and key in NULLABLE_SCORE_KEYS:
                continue
            if (
                not isinstance(item, (int, float))
                or isinstance(item, bool)
                or not math.isfinite(item)
                or not 0 <= item <= 1
            ):
                raise PublicationExportError(f"projection.scores.{key} must be a finite number in [0,1]")
        elif key == "n":
            if not isinstance(item, int) or isinstance(item, bool) or item < 0:
                raise PublicationExportError("projection.scores.n must be a non-negative integer")
        elif key == "partial_composite_scope":
            if item != "measured_headline_axes":
                raise PublicationExportError("projection.scores.partial_composite_scope is unsupported")
        elif not isinstance(item, str) or not item:
            raise PublicationExportError(f"projection.scores.{key} must be a non-empty string")
    return parsed


def validate_community_tree(community_dir: Path) -> None:
    index = _object(json.loads((community_dir / "index.json").read_bytes()), "community index")
    _exact_keys(index, {"groups", "schema_version"}, "community index")
    if index.get("schema_version") != SCHEMA_VERSION:
        raise PublicationExportError("community index schema version mismatch")
    expected_files = {"index.json", "publication-build.json"}
    for index_group in _objects(index.get("groups"), "community index.groups"):
        _exact_keys(
            index_group,
            {"community_model_group_id", "group_path", "n_variants"},
            "community index group",
        )
        group_id = group_id_text(_text(index_group, "community_model_group_id"))
        suffix = group_id.removeprefix("community-group:")
        expected_group_path = f"community/groups/{suffix}.json"
        if index_group.get("group_path") != expected_group_path:
            raise PublicationExportError("community index group path mismatch")
        group_relative = f"groups/{suffix}.json"
        expected_files.add(group_relative)
        group = _object(json.loads((community_dir / group_relative).read_bytes()), "community group")
        _validate_group(group, group_id, _integer(index_group.get("n_variants"), "n_variants"))
    _object(json.loads((community_dir / "publication-build.json").read_bytes()), "community publication build")
    actual_files = {
        path.relative_to(community_dir).as_posix()
        for path in community_dir.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise PublicationExportError("staged community tree contains unexpected or missing files")


def _validate_group(group: dict[str, Any], group_id: str, expected_variants: int) -> None:
    _exact_keys(
        group,
        {"community_model_group_id", "identity_label", "ranked", "schema_version", "variants"},
        "community group",
    )
    if group.get("community_model_group_id") != group_id:
        raise PublicationExportError("community group id mismatch")
    if group.get("identity_label") != IDENTITY_LABEL or group.get("ranked") is not False:
        raise PublicationExportError("community group identity or ranking marker is invalid")
    if group.get("schema_version") != SCHEMA_VERSION:
        raise PublicationExportError("community group schema version mismatch")
    variants = _objects(group.get("variants"), "community group.variants")
    if len(variants) != expected_variants:
        raise PublicationExportError("community group variant count mismatch")
    for variant in variants:
        allowed = {
            "artifact_sha256", "display_name", "lineage_enrichment", "projection_object_sha256",
            "quant_label", "ranked", "scores", "submission_id",
        }
        if set(variant) - allowed or set(variant) < allowed - {"lineage_enrichment"}:
            raise PublicationExportError("community variant fields are invalid")
        artifact = sha256(_text(variant, "artifact_sha256"), "artifact sha256")
        sha256(_text(variant, "projection_object_sha256"), "projection object sha256")
        if variant.get("ranked") is not False:
            raise PublicationExportError("community variant ranking marker is invalid")
        for key in ("display_name", "quant_label"):
            if variant.get(key) is not None and not isinstance(variant.get(key), str):
                raise PublicationExportError(f"community variant {key} must be a string or null")
        if not _text(variant, "submission_id"):
            raise PublicationExportError("community variant submission id must not be empty")
        scores(variant.get("scores"))
        if "lineage_enrichment" in variant:
            _lineage_entry(variant["lineage_enrichment"], artifact)


def sha256(value: str, label: str) -> str:
    if SHA256_RE.fullmatch(value) is None:
        raise PublicationExportError(f"{label} must be 64 lowercase hexadecimal characters")
    return value


def group_id_text(value: str) -> str:
    if GROUP_ID_RE.fullmatch(value) is None:
        raise PublicationExportError("community model group id must match community-group:[0-9a-f]{32}")
    return value


def _revision(value: str, label: str) -> str:
    if REVISION_RE.fullmatch(value) is None:
        raise PublicationExportError(f"{label} must be 40 lowercase hexadecimal characters")
    return value


def _repo_id(value: str, label: str) -> str:
    if REPO_ID_RE.fullmatch(value) is None:
        raise PublicationExportError(f"{label} must match owner/name")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise PublicationExportError(f"{label} fields are invalid")


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

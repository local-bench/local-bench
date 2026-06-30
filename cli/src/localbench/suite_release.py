from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from localbench._types import JsonObject
from localbench.scoring.axes import AXES, axis_membership
from localbench.scoring.scorecard import scorecard_identity
from localbench.submissions.canon import canonical_json_hash, sha256_file
from localbench.submissions.contracts import SUITE_RELEASE_MANIFEST_SCHEMA_VERSION
from localbench.suite_errors import SuiteResolutionError
from localbench.suite_verify import license_manifest, read_json_object, verify_suite_dir


@dataclass(frozen=True, slots=True)
class CoverageProfile:
    profile_id: str
    benches: tuple[str, ...]
    headline_weight: float
    rank_scope: str


COVERAGE_PROFILES: Final[dict[str, CoverageProfile]] = {
    "core-text-3axis-v1": CoverageProfile(
        profile_id="core-text-3axis-v1",
        benches=("mmlu_pro", "ifbench", "tc_json_v1"),
        headline_weight=0.40,
        rank_scope="core-text-3axis-v1",
    ),
    "partial-text-code-4axis-v1": CoverageProfile(
        profile_id="partial-text-code-4axis-v1",
        benches=("mmlu_pro", "ifbench", "tc_json_v1", "lcb"),
        headline_weight=0.50,
        rank_scope="partial-text-code-4axis-v1",
    ),
}


def build_suite_release_manifest(
    suite_dir: Path,
    *,
    coverage_profile_id: str,
) -> JsonObject:
    verify_suite_dir(suite_dir)
    profile = _coverage_profile(coverage_profile_id)
    suite = read_json_object(suite_dir / "suite.json")
    scorecard = scorecard_identity()
    manifest: JsonObject = {
        "schema_version": SUITE_RELEASE_MANIFEST_SCHEMA_VERSION,
        "suite_release_id": _suite_release_id(suite, profile),
        "suite_semver": _suite_semver(suite),
        "suite_hash_algorithm": "sha256-canonical-json-v1",
        "files": _file_manifest(suite_dir),
        "item_set_hashes": _item_set_hashes(suite_dir),
        "axis_membership": {
            axis: list(benches) for axis, benches in axis_membership().items()
        },
        "bench_membership": _bench_membership(),
        "scorecard_id": str(scorecard["scorecard_id"]),
        "registry_digest": str(scorecard["registry_digest"]),
        "scorer_versions": dict(scorecard["scorer_versions"]),
        "license_manifest_sha256": canonical_json_hash(license_manifest(suite, suite_dir)),
        "coverage_profile_id": profile.profile_id,
        "coverage_profile": {
            "benches": list(profile.benches),
            "headline_weight": profile.headline_weight,
            "rank_scope": profile.rank_scope,
        },
    }
    manifest["suite_manifest_sha256"] = suite_manifest_sha256(manifest)
    return manifest


def suite_manifest_sha256(manifest: JsonObject) -> str:
    hashed = {key: value for key, value in manifest.items() if key != "suite_manifest_sha256"}
    return canonical_json_hash(hashed)


def coverage_profile_for_benches(benches: set[str]) -> CoverageProfile:
    for profile in COVERAGE_PROFILES.values():
        if set(profile.benches) == benches:
            return profile
    if {"mmlu_pro", "ifbench", "tc_json_v1", "lcb"}.issubset(benches):
        return COVERAGE_PROFILES["partial-text-code-4axis-v1"]
    if {"mmlu_pro", "ifbench", "tc_json_v1"}.issubset(benches):
        return COVERAGE_PROFILES["core-text-3axis-v1"]
    return CoverageProfile(
        profile_id="custom-partial-v1",
        benches=tuple(sorted(benches)),
        headline_weight=_headline_weight(benches),
        rank_scope="custom-partial-v1",
    )


def _coverage_profile(profile_id: str) -> CoverageProfile:
    profile = COVERAGE_PROFILES.get(profile_id)
    if profile is None:
        raise SuiteResolutionError(f"unknown coverage profile: {profile_id}")
    return profile


def _suite_release_id(suite: JsonObject, profile: CoverageProfile) -> str:
    return f"{_suite_semver(suite)}-{profile.profile_id}"


def _suite_semver(suite: JsonObject) -> str:
    value = suite.get("version") or suite.get("id")
    return value if isinstance(value, str) and value else "suite-v1"


def _file_manifest(suite_dir: Path) -> list[JsonObject]:
    files: list[JsonObject] = []
    for path in sorted(
        (item for item in suite_dir.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(suite_dir).as_posix(),
    ):
        relative = path.relative_to(suite_dir).as_posix()
        files.append({"path": relative, "sha256": sha256_file(path), "size": path.stat().st_size})
    return files


def _item_set_hashes(suite_dir: Path) -> JsonObject:
    lock = read_json_object(suite_dir / "itemsets.lock.json")
    files = lock.get("files")
    if not isinstance(files, dict):
        return {}
    hashes: dict[str, str] = {}
    for file_name, raw in files.items():
        if isinstance(file_name, str) and isinstance(raw, dict) and isinstance(raw.get("sha256"), str):
            hashes[file_name] = raw["sha256"]
    return hashes


def _bench_membership() -> JsonObject:
    return {
        bench: axis
        for axis, benches in axis_membership().items()
        for bench in benches
    }


def _headline_weight(benches: set[str]) -> float:
    return sum(axis.weight for axis in AXES if benches.intersection(axis.benches))


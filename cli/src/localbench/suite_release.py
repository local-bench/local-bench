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

SUITE_RELEASE_MANIFEST_FILE: Final = "suite_release_manifest.json"


@dataclass(frozen=True, slots=True)
class CoverageProfile:
    profile_id: str
    benches: tuple[str, ...]
    headline_weight: float
    rank_scope: str
    rankable: bool = True
    legacy: bool = False


COVERAGE_PROFILES: Final[dict[str, CoverageProfile]] = {
    "full-exec-6axis-v1": CoverageProfile(
        profile_id="full-exec-6axis-v1",
        benches=(
            "mmlu_pro",
            "ifbench",
            "tc_json_v1",
            "bigcodebench_hard",
            "olymmath_hard",
            "amo",
            "appworld_c",
        ),
        headline_weight=1.00,
        rank_scope="full-exec-6axis-v1",
    ),
    "static-exec-5axis-v1": CoverageProfile(
        profile_id="static-exec-5axis-v1",
        benches=(
            "mmlu_pro",
            "ifbench",
            "tc_json_v1",
            "bigcodebench_hard",
            "olymmath_hard",
            "amo",
        ),
        headline_weight=0.60,
        rank_scope="static-exec-5axis-v1",
    ),
    "static-core-diag-v1": CoverageProfile(
        profile_id="static-core-diag-v1",
        benches=("mmlu_pro", "ifbench", "tc_json_v1", "olymmath_hard", "amo"),
        headline_weight=0.45,
        rank_scope="diagnostic",
        rankable=False,
    ),
    "core-text-3axis-v1": CoverageProfile(
        profile_id="core-text-3axis-v1",
        benches=("mmlu_pro", "ifbench", "tc_json_v1"),
        headline_weight=0.40,
        rank_scope="core-text-3axis-v1",
        legacy=True,
    ),
    "partial-text-code-4axis-v1": CoverageProfile(
        profile_id="partial-text-code-4axis-v1",
        benches=("mmlu_pro", "ifbench", "tc_json_v1", "lcb"),
        headline_weight=0.50,
        rank_scope="partial-text-code-4axis-v1",
        legacy=True,
    ),
    "text-code-agentic-5axis-v1": CoverageProfile(
        profile_id="text-code-agentic-5axis-v1",
        benches=("mmlu_pro", "ifbench", "tc_json_v1", "lcb", "appworld_c"),
        headline_weight=1.00,
        rank_scope="text-code-agentic-5axis-v1",
        legacy=True,
    ),
}

_LEGACY_REGISTRY_DIGEST: Final = "17f3669254a8bd152526d69a484c24050aa85cfbc73bd9781cd48997c51562f8"
_LEGACY_SCORECARD_ID: Final = "8359c46daa85232ac32b9a2bd9b54f5ba6dfb7b0e0acd7669caa05c3bfdbb896"
_LEGACY_AXIS_MEMBERSHIP: Final[dict[str, list[str]]] = {
    "agentic": ["appworld_c"],
    "coding": ["lcb"],
    "instruction_following": ["ifbench"],
    "knowledge": ["mmlu_pro"],
    "long_context": ["ruler_32k"],
    "math": ["olymmath_hard", "amo"],
    "tool_calling": ["tc_json_v1"],
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
    axis_members = _axis_membership(profile)
    bench_members = _bench_membership(axis_members)
    coverage: JsonObject = {
        "benches": list(profile.benches),
        "headline_weight": profile.headline_weight,
        "rank_scope": profile.rank_scope,
    }
    if not profile.legacy:
        coverage["rankable"] = profile.rankable
        coverage["legacy"] = profile.legacy
    manifest: JsonObject = {
        "schema_version": SUITE_RELEASE_MANIFEST_SCHEMA_VERSION,
        "suite_release_id": _suite_release_id(suite, profile),
        "suite_semver": _suite_semver(suite),
        "suite_hash_algorithm": "sha256-canonical-json-v1",
        "files": _file_manifest(suite_dir),
        "item_set_hashes": _item_set_hashes(suite_dir),
        "axis_membership": axis_members,
        "bench_membership": bench_members,
        "scorecard_id": _scorecard_id(profile, scorecard),
        "registry_digest": _registry_digest(profile, scorecard),
        "scorer_versions": dict(scorecard["scorer_versions"]),
        "license_manifest_sha256": canonical_json_hash(license_manifest(suite, suite_dir)),
        "license_flags": _license_flags(suite_dir),
        "coverage_profile_id": profile.profile_id,
        "coverage_profile": coverage,
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
    if set(COVERAGE_PROFILES["full-exec-6axis-v1"].benches).issubset(benches):
        return COVERAGE_PROFILES["full-exec-6axis-v1"]
    if set(COVERAGE_PROFILES["static-exec-5axis-v1"].benches).issubset(benches):
        return COVERAGE_PROFILES["static-exec-5axis-v1"]
    if set(COVERAGE_PROFILES["static-core-diag-v1"].benches).issubset(benches):
        return COVERAGE_PROFILES["static-core-diag-v1"]
    if {"mmlu_pro", "ifbench", "tc_json_v1", "lcb", "appworld_c"}.issubset(benches):
        return COVERAGE_PROFILES["text-code-agentic-5axis-v1"]
    if {"mmlu_pro", "ifbench", "tc_json_v1", "lcb"}.issubset(benches):
        return COVERAGE_PROFILES["partial-text-code-4axis-v1"]
    if {"mmlu_pro", "ifbench", "tc_json_v1"}.issubset(benches):
        return COVERAGE_PROFILES["core-text-3axis-v1"]
    return CoverageProfile(
        profile_id="custom-partial-v1",
        benches=tuple(sorted(benches)),
        headline_weight=_headline_weight(benches),
        rank_scope="custom-partial-v1",
        rankable=False,
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
        if relative == SUITE_RELEASE_MANIFEST_FILE:
            continue
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


def _axis_membership(profile: CoverageProfile) -> JsonObject:
    if profile.legacy:
        return {axis: list(benches) for axis, benches in _LEGACY_AXIS_MEMBERSHIP.items()}
    return {axis: list(benches) for axis, benches in axis_membership().items()}


def _bench_membership(axis_members: JsonObject) -> JsonObject:
    return {
        bench: axis
        for axis, benches in axis_members.items()
        for bench in benches
    }


def _scorecard_id(profile: CoverageProfile, scorecard: JsonObject) -> str:
    return _LEGACY_SCORECARD_ID if profile.legacy else str(scorecard["scorecard_id"])


def _registry_digest(profile: CoverageProfile, scorecard: JsonObject) -> str:
    return _LEGACY_REGISTRY_DIGEST if profile.legacy else str(scorecard["registry_digest"])


def _license_flags(suite_dir: Path) -> list[JsonObject]:
    lock = read_json_object(suite_dir / "itemsets.lock.json")
    files = lock.get("files")
    if not isinstance(files, dict) or "lcb.jsonl" not in files:
        return []
    return [
        {
            "path": "lcb.jsonl",
            "status": "source_tos_notice",
            "note": (
                "LiveCodeBench test-generation items are CC-BY-4.0, but source problem "
                "statements originate from LeetCode; public serving carries this NOTICE "
                "instead of treating redistribution terms as fully settled."
            ),
        },
    ]


def _headline_weight(benches: set[str]) -> float:
    return sum(axis.weight for axis in AXES if benches.intersection((*axis.benches, *axis.legacy_benches)))

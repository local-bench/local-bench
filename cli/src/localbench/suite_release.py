from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
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


@dataclass(frozen=True, slots=True)
class FrozenScoringSnapshot:
    axis_membership: tuple[tuple[str, tuple[str, ...]], ...]
    registry_digest: str
    scorecard_id: str
    scorer_versions: tuple[tuple[str, str], ...]


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
_LEGACY_SCORER_VERSIONS: Final[dict[str, str]] = {
    "amo": "1",
    "appworld_c": "1",
    "bfcl": "1",
    "bfcl_multi_turn": "1",
    "bigcodebench_hard": "1",
    "genmath": "1",
    "ifbench": "1",
    "ifeval": "1",
    "lcb": "1",
    "mmlu_pro": "1",
    "olymmath_hard": "1",
    "ruler_32k": "1",
    "supergpqa": "1",
    "tc_json_v1": "1",
}
_LEGACY_AXIS_MEMBERSHIP: Final[dict[str, list[str]]] = {
    "agentic": ["appworld_c"],
    "coding": ["lcb"],
    "instruction_following": ["ifbench"],
    "knowledge": ["mmlu_pro"],
    "long_context": ["ruler_32k"],
    "math": ["olymmath_hard", "amo"],
    "tool_calling": ["tc_json_v1"],
}

_V1_EXEC_SCORING_SNAPSHOT: Final = FrozenScoringSnapshot(
    axis_membership=(
        ("agentic", ("appworld_c",)),
        ("coding", ("bigcodebench_hard",)),
        ("instruction_following", ("ifbench",)),
        ("knowledge", ("mmlu_pro",)),
        ("long_context", ("ruler_32k",)),
        ("math", ("olymmath_hard", "amo")),
        ("tool_calling", ("tc_json_v1",)),
    ),
    registry_digest="16c189f04e7317756155e578254ecb5ae2d63c7c687528206851fdbe7fce4227",
    scorecard_id="b849e307e27b00d2f872ad7b294ac67d848610abfa0611bc66c402f65de2c20c",
    scorer_versions=(
        ("amo", "1"),
        ("appworld_c", "1"),
        ("bfcl", "1"),
        ("bfcl_multi_turn", "1"),
        ("bigcodebench_hard", (
            "1+bcbh-scoreable-v1+bigcodebench-ast-gate-v2+bigcodebench-invert-control-sentinel-v2"
        )),
        ("genmath", "1"),
        ("ifbench", "1"),
        ("ifeval", "1"),
        ("lcb", "1"),
        ("mmlu_pro", "1"),
        ("olymmath_hard", "1"),
        ("ruler_32k", "1"),
        ("supergpqa", "1"),
        ("tc_json_v1", "1"),
    ),
)

_V1_STATIC_CORE_DIAG_SCORING_SNAPSHOT: Final = FrozenScoringSnapshot(
    axis_membership=(
        ("agentic", ("appworld_c",)),
        ("coding", ("bigcodebench_hard",)),
        ("instruction_following", ("ifbench",)),
        ("knowledge", ("mmlu_pro",)),
        ("long_context", ("ruler_32k",)),
        ("math", ("olymmath_hard", "amo")),
        ("tool_calling", ("tc_json_v1",)),
    ),
    registry_digest="16c189f04e7317756155e578254ecb5ae2d63c7c687528206851fdbe7fce4227",
    scorecard_id="b849e307e27b00d2f872ad7b294ac67d848610abfa0611bc66c402f65de2c20c",
    scorer_versions=(
        ("amo", "1"),
        ("appworld_c", "1"),
        ("bfcl", "1"),
        ("bfcl_multi_turn", "1"),
        ("bigcodebench_hard", (
            "1+bcbh-scoreable-v1+bigcodebench-ast-gate-v2+bigcodebench-invert-control-sentinel-v2"
        )),
        ("genmath", "1"),
        ("ifbench", "1"),
        ("ifeval", "1"),
        ("lcb", "1"),
        ("mmlu_pro", "1"),
        ("olymmath_hard", "1"),
        ("ruler_32k", "1"),
        ("supergpqa", "1"),
        ("tc_json_v1", "1"),
    ),
)

_FROZEN_PROFILE_SCORING: Final[dict[str, FrozenScoringSnapshot]] = {
    "full-exec-6axis-v1": _V1_EXEC_SCORING_SNAPSHOT,
    "static-exec-5axis-v1": _V1_EXEC_SCORING_SNAPSHOT,
    "static-core-diag-v1": _V1_STATIC_CORE_DIAG_SCORING_SNAPSHOT,
}


def build_suite_release_manifest(
    suite_dir: Path,
    *,
    coverage_profile_id: str,
) -> JsonObject:
    verify_suite_dir(suite_dir)
    profile = _coverage_profile(coverage_profile_id)
    suite = read_json_object(suite_dir / "suite.json")
    frozen_scoring = _FROZEN_PROFILE_SCORING.get(profile.profile_id)
    scorecard = None if frozen_scoring is not None else scorecard_identity()
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
        "scorer_versions": _scorer_versions(profile, scorecard),
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


def verify_suite_release_files(suite_dir: Path, manifest: JsonObject) -> None:
    """Bind every file in a release manifest to the selected suite directory."""
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise SuiteResolutionError("suite release manifest must contain a non-empty files array")
    suite_root = suite_dir.resolve()
    seen: set[str] = set()
    for index, raw in enumerate(files):
        if not isinstance(raw, dict):
            raise SuiteResolutionError(f"suite release manifest files[{index}] must be an object")
        relative = raw.get("path")
        expected_sha = raw.get("sha256")
        expected_size = raw.get("size")
        if not isinstance(relative, str) or not relative:
            raise SuiteResolutionError(f"suite release manifest files[{index}] has invalid path")
        posix_path = PurePosixPath(relative)
        if posix_path.is_absolute() or ".." in posix_path.parts or "\\" in relative:
            raise SuiteResolutionError(f"unsafe suite release manifest path: {relative}")
        if relative in seen:
            raise SuiteResolutionError(f"duplicate suite release manifest path: {relative}")
        seen.add(relative)
        if not isinstance(expected_sha, str) or len(expected_sha) != 64:
            raise SuiteResolutionError(f"{relative}: invalid release manifest sha256")
        if not isinstance(expected_size, int) or isinstance(expected_size, bool) or expected_size < 0:
            raise SuiteResolutionError(f"{relative}: invalid release manifest size")
        path = suite_dir.joinpath(*posix_path.parts)
        try:
            resolved_path = path.resolve(strict=True)
            if not resolved_path.is_relative_to(suite_root):
                raise SuiteResolutionError(f"release-manifest path escapes suite directory: {relative}")
            if not resolved_path.is_file():
                raise SuiteResolutionError(f"release-manifest path is not a file: {path}")
            actual_size = resolved_path.stat().st_size
        except FileNotFoundError as error:
            raise SuiteResolutionError(f"missing release-manifest file: {path}") from error
        except OSError as error:
            raise SuiteResolutionError(f"cannot inspect release-manifest file {path}: {error}") from error
        if actual_size != expected_size:
            raise SuiteResolutionError(
                f"{relative}: release manifest size mismatch {actual_size} != {expected_size}",
            )
        try:
            actual_sha = sha256_file(resolved_path)
        except OSError as error:
            raise SuiteResolutionError(f"cannot hash release-manifest file {path}: {error}") from error
        if actual_sha != expected_sha:
            raise SuiteResolutionError(
                f"{relative}: release manifest sha256 mismatch {actual_sha} != {expected_sha}",
            )


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
    frozen = _FROZEN_PROFILE_SCORING.get(profile.profile_id)
    if frozen is not None:
        return {axis: list(benches) for axis, benches in frozen.axis_membership}
    if profile.legacy:
        return {axis: list(benches) for axis, benches in _LEGACY_AXIS_MEMBERSHIP.items()}
    return {axis: list(benches) for axis, benches in axis_membership().items()}


def _bench_membership(axis_members: JsonObject) -> JsonObject:
    return {
        bench: axis
        for axis, benches in axis_members.items()
        for bench in benches
    }


def _scorecard_id(profile: CoverageProfile, scorecard: JsonObject | None) -> str:
    frozen = _FROZEN_PROFILE_SCORING.get(profile.profile_id)
    if frozen is not None:
        return frozen.scorecard_id
    if profile.legacy:
        return _LEGACY_SCORECARD_ID
    if scorecard is None:
        raise AssertionError("live coverage profiles require a scorecard identity")
    return str(scorecard["scorecard_id"])


def _registry_digest(profile: CoverageProfile, scorecard: JsonObject | None) -> str:
    frozen = _FROZEN_PROFILE_SCORING.get(profile.profile_id)
    if frozen is not None:
        return frozen.registry_digest
    if profile.legacy:
        return _LEGACY_REGISTRY_DIGEST
    if scorecard is None:
        raise AssertionError("live coverage profiles require a scorecard identity")
    return str(scorecard["registry_digest"])


def _scorer_versions(profile: CoverageProfile, scorecard: JsonObject | None) -> dict[str, str]:
    frozen = _FROZEN_PROFILE_SCORING.get(profile.profile_id)
    if frozen is not None:
        return dict(frozen.scorer_versions)
    if profile.legacy:
        return dict(_LEGACY_SCORER_VERSIONS)
    if scorecard is None:
        raise AssertionError("live coverage profiles require a scorecard identity")
    return dict(scorecard["scorer_versions"])


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

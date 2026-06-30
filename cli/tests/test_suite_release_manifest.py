from __future__ import annotations

import json
from pathlib import Path

from localbench._types import JsonObject
from localbench.scoring.axes import axis_membership
from localbench.suite_release import (
    COVERAGE_PROFILES,
    build_suite_release_manifest,
    suite_manifest_sha256,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUITE_V1 = _REPO_ROOT / "suite" / "v1"
_SITE_4AXIS = _REPO_ROOT / "web" / "public" / "suites" / "suite-v1-partial-text-code-4axis-v1"
_SITE_MANIFEST = _SITE_4AXIS / "suite_release_manifest.json"


def test_coverage_profiles_define_current_partial_scopes() -> None:
    # Given / When / Then: the two frozen coverage profiles carry explicit scoped membership.
    assert COVERAGE_PROFILES["core-text-3axis-v1"].benches == (
        "mmlu_pro",
        "ifbench",
        "tc_json_v1",
    )
    assert COVERAGE_PROFILES["core-text-3axis-v1"].headline_weight == 0.40
    assert COVERAGE_PROFILES["partial-text-code-4axis-v1"].benches == (
        "mmlu_pro",
        "ifbench",
        "tc_json_v1",
        "lcb",
    )
    assert COVERAGE_PROFILES["partial-text-code-4axis-v1"].headline_weight == 0.50


def test_suite_release_manifest_hashes_canonical_serialization() -> None:
    # Given: a suite release generated from suite/v1 and the 4-axis partial profile.
    manifest = build_suite_release_manifest(_SUITE_V1, coverage_profile_id="partial-text-code-4axis-v1")

    # When: its canonical hash is recomputed.
    digest = suite_manifest_sha256(manifest)

    # Then: the embedded hash is stable and derived from canonical manifest content.
    assert manifest["schema_version"] == "localbench.suite_release_manifest.v1"
    assert manifest["suite_hash_algorithm"] == "sha256-canonical-json-v1"
    assert manifest["suite_manifest_sha256"] == digest
    assert digest == suite_manifest_sha256(
        build_suite_release_manifest(_SUITE_V1, coverage_profile_id="partial-text-code-4axis-v1"),
    )
    assert manifest["coverage_profile_id"] == "partial-text-code-4axis-v1"


def test_suite_release_membership_is_generated_from_axes_registry() -> None:
    # Given / When: the release manifest is generated.
    manifest = build_suite_release_manifest(_SUITE_V1, coverage_profile_id="partial-text-code-4axis-v1")

    # Then: every axis membership, including agentic, matches axes.py exactly.
    expected = {axis: list(benches) for axis, benches in axis_membership().items()}
    assert manifest["axis_membership"] == expected
    assert manifest["axis_membership"]["agentic"] == ["appworld_c"]
    assert manifest["bench_membership"]["appworld_c"] == "agentic"


def test_site_serves_4axis_release_with_canonical_manifest_and_lcb_notice() -> None:
    # Given: the site-served Batch 2a suite release.
    manifest = read_json(_SITE_MANIFEST)

    # When: its canonical suite manifest hash is recomputed.
    digest = suite_manifest_sha256(manifest)

    # Then: the immutable public directory represents the 4-axis partial profile.
    assert manifest["schema_version"] == "localbench.suite_release_manifest.v1"
    assert manifest["suite_release_id"] == "suite-v1-partial-text-code-4axis-v1"
    assert manifest["coverage_profile_id"] == "partial-text-code-4axis-v1"
    assert manifest["suite_manifest_sha256"] == digest
    assert manifest["coverage_profile"]["benches"] == ["mmlu_pro", "ifbench", "tc_json_v1", "lcb"]
    assert _manifest_paths(manifest) >= {
        "suite.json",
        "itemsets.lock.json",
        "mmlu_pro.jsonl",
        "ifbench.jsonl",
        "tc_json_v1.jsonl",
        "lcb.jsonl",
        "NOTICE",
    }
    assert not any("C:" in path or "\\" in path for path in _manifest_paths(manifest))
    assert {
        "path": "lcb.jsonl",
        "status": "source_tos_notice",
    } in [
        {"path": flag["path"], "status": flag["status"]}
        for flag in manifest["license_flags"]
    ]
    assert "LiveCodeBench" in (_SITE_4AXIS / "NOTICE").read_text(encoding="utf-8")


def test_site_4axis_release_manifest_matches_foundation_builder() -> None:
    # Given: the committed site release directory and its manifest.
    manifest = read_json(_SITE_MANIFEST)

    # When: the foundation manifest builder runs over that same served directory.
    rebuilt = build_suite_release_manifest(_SITE_4AXIS, coverage_profile_id="partial-text-code-4axis-v1")

    # Then: the checked-in release is exactly the canonical foundation output.
    assert manifest == rebuilt


def read_json(path: Path) -> JsonObject:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _manifest_paths(manifest: JsonObject) -> set[str]:
    return {
        str(file_entry["path"])
        for file_entry in manifest["files"]
        if isinstance(file_entry, dict)
    }

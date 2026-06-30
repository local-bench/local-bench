from __future__ import annotations

from pathlib import Path

from localbench.scoring.axes import axis_membership
from localbench.suite_release import (
    COVERAGE_PROFILES,
    build_suite_release_manifest,
    suite_manifest_sha256,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUITE_V1 = _REPO_ROOT / "suite" / "v1"


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

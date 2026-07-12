from __future__ import annotations

import json
from pathlib import Path

import pytest

import localbench.scoring.axes as axes_module
import localbench.scoring.scorecard as scorecard_module
from localbench._types import JsonObject
from localbench.scoring.axes import Axis, axis_membership
from localbench.scoring.scorecard import scorecard_identity
from localbench.suite_release import (
    COVERAGE_PROFILES,
    build_suite_release_manifest,
    coverage_profile_for_benches,
    suite_manifest_sha256,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUITE_V1 = _REPO_ROOT / "suite" / "v1"
_SITE_4AXIS = _REPO_ROOT / "web" / "public" / "suites" / "suite-v1-partial-text-code-4axis-v1"
_SITE_MANIFEST = _SITE_4AXIS / "suite_release_manifest.json"
_SITE_5AXIS = _REPO_ROOT / "web" / "public" / "suites" / "suite-v1-text-code-agentic-5axis-v1"
_SITE_5AXIS_MANIFEST = _SITE_5AXIS / "suite_release_manifest.json"
_EXPECTED_RELEASE_PAIRS = _REPO_ROOT / "suite" / "release-pairs.expected.json"


def test_coverage_profiles_define_current_partial_scopes() -> None:
    # Given / When / Then: legacy profiles remain registered and flagged legacy.
    assert COVERAGE_PROFILES["core-text-3axis-v1"].benches == (
        "mmlu_pro",
        "ifbench",
        "tc_json_v1",
    )
    assert COVERAGE_PROFILES["core-text-3axis-v1"].legacy is True
    assert COVERAGE_PROFILES["core-text-3axis-v1"].headline_weight == 0.40
    assert COVERAGE_PROFILES["partial-text-code-4axis-v1"].benches == (
        "mmlu_pro",
        "ifbench",
        "tc_json_v1",
        "lcb",
    )
    assert COVERAGE_PROFILES["partial-text-code-4axis-v1"].legacy is True
    assert COVERAGE_PROFILES["partial-text-code-4axis-v1"].headline_weight == 0.50
    assert COVERAGE_PROFILES["text-code-agentic-5axis-v1"].benches == (
        "mmlu_pro",
        "ifbench",
        "tc_json_v1",
        "lcb",
        "appworld_c",
    )
    assert COVERAGE_PROFILES["text-code-agentic-5axis-v1"].legacy is True
    assert COVERAGE_PROFILES["text-code-agentic-5axis-v1"].headline_weight == 1.00
    assert COVERAGE_PROFILES["full-exec-6axis-v1"].benches == (
        "mmlu_pro",
        "ifbench",
        "tc_json_v1",
        "bigcodebench_hard",
        "olymmath_hard",
        "amo",
        "appworld_c",
    )
    assert COVERAGE_PROFILES["full-exec-6axis-v1"].rankable is True
    assert COVERAGE_PROFILES["full-exec-6axis-v1"].legacy is False
    assert COVERAGE_PROFILES["static-exec-5axis-v1"].benches == (
        "mmlu_pro",
        "ifbench",
        "tc_json_v1",
        "bigcodebench_hard",
        "olymmath_hard",
        "amo",
    )
    assert COVERAGE_PROFILES["static-exec-5axis-v1"].rankable is True
    assert COVERAGE_PROFILES["static-core-diag-v1"].benches == (
        "mmlu_pro",
        "ifbench",
        "tc_json_v1",
        "olymmath_hard",
        "amo",
    )
    assert COVERAGE_PROFILES["static-core-diag-v1"].rankable is False


def test_coverage_profile_for_benches_preserves_four_axis_and_matches_five_axis() -> None:
    # Given: four-axis and five-axis measured bench sets.
    four_axis = {"mmlu_pro", "ifbench", "tc_json_v1", "lcb"}
    five_axis = {"mmlu_pro", "ifbench", "tc_json_v1", "lcb", "appworld_c"}

    # When: coverage profiles are inferred from measured benches.
    four_axis_profile = coverage_profile_for_benches(four_axis)
    five_axis_profile = coverage_profile_for_benches(five_axis)

    # Then: the 5-axis set does not get swallowed by the 4-axis subset fallback.
    assert four_axis_profile.profile_id == "partial-text-code-4axis-v1"
    assert four_axis_profile.rank_scope == "partial-text-code-4axis-v1"
    assert five_axis_profile.profile_id == "text-code-agentic-5axis-v1"
    assert five_axis_profile.rank_scope == "text-code-agentic-5axis-v1"


def test_coverage_profile_for_benches_prefers_v2_exec_releases() -> None:
    full = {
        "mmlu_pro",
        "ifbench",
        "tc_json_v1",
        "bigcodebench_hard",
        "olymmath_hard",
        "amo",
        "appworld_c",
    }
    static = full - {"appworld_c"}
    static_core = static - {"bigcodebench_hard"}

    assert coverage_profile_for_benches(full).profile_id == "full-exec-6axis-v1"
    assert coverage_profile_for_benches(static).profile_id == "static-exec-5axis-v1"
    diagnostic = coverage_profile_for_benches(static_core)
    assert diagnostic.profile_id == "static-core-diag-v1"
    assert diagnostic.rank_scope == "diagnostic"


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


@pytest.mark.parametrize(
    ("profile_id", "release_id", "expected_sha"),
    (
        (
            "full-exec-6axis-v1",
            "suite-v1-full-exec-6axis-v1",
            "c4098df81440c4489ee8c6d6967f3a5d6f9d6941810779abd135326ad734f468",
        ),
        (
            "static-exec-5axis-v1",
            "suite-v1-static-exec-5axis-v1",
            "4e240f8cffe8826ef1fd723f54b4b789d93990851d838818bce0954a38c61d64",
        ),
    ),
)
def test_v1_exec_release_manifest_shas_are_unchanged(
    profile_id: str,
    release_id: str,
    expected_sha: str,
) -> None:
    manifest = build_suite_release_manifest(_SUITE_V1, coverage_profile_id=profile_id)

    assert manifest["suite_release_id"] == release_id
    assert manifest["suite_manifest_sha256"] == expected_sha
    assert suite_manifest_sha256(manifest) == expected_sha


@pytest.mark.parametrize(
    ("profile_id", "release_id", "expected_sha"),
    (
        (
            "full-exec-6axis-v1",
            "suite-v1-full-exec-6axis-v1",
            "c4098df81440c4489ee8c6d6967f3a5d6f9d6941810779abd135326ad734f468",
        ),
        (
            "static-exec-5axis-v1",
            "suite-v1-static-exec-5axis-v1",
            "4e240f8cffe8826ef1fd723f54b4b789d93990851d838818bce0954a38c61d64",
        ),
    ),
)
def test_v1_exec_release_manifest_identity_is_frozen_against_live_registry_perturbation(
    monkeypatch: pytest.MonkeyPatch,
    profile_id: str,
    release_id: str,
    expected_sha: str,
) -> None:
    # Given: a future live registry and scorecard identity that differ from v1.
    perturbed_scorecard = _perturb_live_scoring_registry(monkeypatch)

    # When: either locked v1 profile is rebuilt.
    manifest = build_suite_release_manifest(_SUITE_V1, coverage_profile_id=profile_id)

    # Then: all scoring identity comes from its frozen snapshot, preserving the pinned release.
    assert manifest["suite_release_id"] == release_id
    assert manifest["suite_manifest_sha256"] == expected_sha
    assert "scratch_candidate" not in manifest["axis_membership"]
    assert "scratch_zero_weight" not in manifest["scorer_versions"]
    assert manifest["registry_digest"] != perturbed_scorecard["registry_digest"]
    assert manifest["scorecard_id"] != perturbed_scorecard["scorecard_id"]


def test_v1_exec_release_membership_matches_its_frozen_registry_snapshot() -> None:
    # Given / When: the v1 release manifest is generated.
    manifest = build_suite_release_manifest(_SUITE_V1, coverage_profile_id="full-exec-6axis-v1")

    # Then: its frozen membership matches the registry at the point v1 was locked.
    expected = {axis: list(benches) for axis, benches in axis_membership().items()}
    assert manifest["axis_membership"] == expected
    assert manifest["axis_membership"]["agentic"] == ["appworld_c"]
    assert manifest["axis_membership"]["coding"] == ["bigcodebench_hard"]
    assert manifest["axis_membership"]["math"] == ["olymmath_hard", "amo"]
    assert manifest["bench_membership"]["appworld_c"] == "agentic"


def test_non_v1_profile_scoring_identity_tracks_live_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the same simulated future live-registry perturbation.
    perturbed_scorecard = _perturb_live_scoring_registry(monkeypatch)

    # When: an unfrozen diagnostic profile is rebuilt.
    manifest = build_suite_release_manifest(_SUITE_V1, coverage_profile_id="static-core-diag-v1")

    # Then: future/non-v1 profiles still consume the live scoring identity.
    assert manifest["axis_membership"]["scratch_candidate"] == ["scratch_zero_weight"]
    assert manifest["bench_membership"]["scratch_zero_weight"] == "scratch_candidate"
    assert manifest["registry_digest"] == perturbed_scorecard["registry_digest"]
    assert manifest["scorecard_id"] == perturbed_scorecard["scorecard_id"]
    assert manifest["scorer_versions"]["scratch_zero_weight"] == "1"


def test_cli_release_pairs_match_shared_fixture() -> None:
    fixture = read_json(_EXPECTED_RELEASE_PAIRS)
    pairs = fixture["pairs"]
    assert isinstance(pairs, list)
    actual: dict[str, str] = {}
    for pair in pairs:
        assert isinstance(pair, dict)
        release_id = str(pair["id"])
        if pair.get("legacy") is True:
            actual[release_id] = str(pair["suite_manifest_sha256"])
            continue
        profile_id = release_id.removeprefix("suite-v1-")
        manifest = build_suite_release_manifest(_SUITE_V1, coverage_profile_id=profile_id)
        actual[release_id] = str(manifest["suite_manifest_sha256"])

    expected = {str(pair["id"]): str(pair["suite_manifest_sha256"]) for pair in pairs if isinstance(pair, dict)}
    assert actual == expected


def test_site_released_suites_map_matches_shared_fixture() -> None:
    # Regression guard for the 2026-07-06 manifest-sha desync: foundation._SITE_RELEASED_SUITES
    # holds a SECOND copy of every release's manifest sha but was not covered by the parity test
    # above, so a scorer-identity bump that updated release-pairs.expected.json left it stale
    # (which would have made the CLI treat real v2 bundles as not-site-released). Every entry in
    # the map must match the single source of truth.
    from localbench.submissions.foundation import _SITE_RELEASED_SUITES

    fixture = read_json(_EXPECTED_RELEASE_PAIRS)
    expected = {str(pair["id"]): str(pair["suite_manifest_sha256"]) for pair in fixture["pairs"]}
    for release_id, sha in _SITE_RELEASED_SUITES.items():
        assert release_id in expected, f"{release_id} in _SITE_RELEASED_SUITES but not the release-pairs fixture"
        assert sha == expected[release_id], (
            f"manifest sha desync for {release_id}: _SITE_RELEASED_SUITES has {sha}, "
            f"release-pairs fixture has {expected[release_id]}"
        )


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


def test_site_5axis_release_manifest_matches_foundation_builder_and_is_hash_stable() -> None:
    # Given: the committed site release directory and its manifest.
    manifest = read_json(_SITE_5AXIS_MANIFEST)

    # When: the foundation manifest builder runs over that same served directory twice.
    first = build_suite_release_manifest(_SITE_5AXIS, coverage_profile_id="text-code-agentic-5axis-v1")
    second = build_suite_release_manifest(_SITE_5AXIS, coverage_profile_id="text-code-agentic-5axis-v1")

    # Then: the checked-in release is exactly reproducible and includes out-of-band agentic membership.
    assert manifest == first
    assert first == second
    assert first["suite_manifest_sha256"] == second["suite_manifest_sha256"]
    assert first["suite_release_id"] == "suite-v1-text-code-agentic-5axis-v1"
    assert first["coverage_profile_id"] == "text-code-agentic-5axis-v1"
    assert first["coverage_profile"]["headline_weight"] == 1.0
    assert first["axis_membership"]["agentic"] == ["appworld_c"]
    assert "appworld_c.jsonl" not in _manifest_paths(first)


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


def _perturb_live_scoring_registry(monkeypatch: pytest.MonkeyPatch) -> JsonObject:
    scratch_axis = Axis(
        key="scratch_candidate",
        display="Scratch Candidate",
        web_key="scratch_candidate",
        benches=("scratch_zero_weight",),
        legacy_benches=(),
        role="candidate",
        weight=0.0,
        web_display=False,
    )
    perturbed_axes = (*axes_module.AXES, scratch_axis)
    monkeypatch.setattr(axes_module, "AXES", perturbed_axes)
    monkeypatch.setattr(scorecard_module, "AXES", perturbed_axes)
    monkeypatch.setattr(
        scorecard_module,
        "SCORER_VERSIONS",
        {**scorecard_module.SCORER_VERSIONS, "scratch_zero_weight": "1"},
    )
    return scorecard_identity()

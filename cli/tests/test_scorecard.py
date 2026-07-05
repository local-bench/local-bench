from __future__ import annotations

from dataclasses import fields, replace

import pytest

import localbench.reasoning_registry as reasoning_registry
from localbench.lane_spec import lane_spec_digest
from localbench.reasoning_registry import QWEN_REASONING_ENTRY
from localbench.scoring.axes import AXES, Axis
from localbench.scoring.scorecard import (
    EXEC_BENCHES,
    SCORER_VERSIONS,
    _digest,
    _registry_payload,
    registry_digest,
    scorecard_identity,
)


def test_registry_payload_hashes_every_axis_field() -> None:
    # The blocker the autoreview caught: hashing a hand-picked subset (omitting
    # web_key/web_display) let a web-scoring change slip through unhashed. Lock the
    # invariant that EVERY Axis field is in the digest payload.
    payload = _registry_payload()
    expected = {field.name for field in fields(Axis)}
    assert payload, "registry payload must not be empty"
    assert all(set(row) == expected for row in payload), "registry payload must hash ALL Axis fields"


def test_scorecard_identity_is_deterministic_and_self_describing() -> None:
    first = scorecard_identity()
    second = scorecard_identity()
    assert first == second
    assert len(first["scorecard_id"]) == 64  # full sha256 hex
    assert first["registry_digest"] == registry_digest()
    assert first["scorecard_version"] == "3"
    assert first["lane_spec_digest"] == lane_spec_digest("capped-thinking-v1")
    assert first["execution_profile_id"] is None
    assert first["execution_profile_digest"] is None
    assert first["execution_profile"] is None
    assert "reasoning_registry" not in first
    assert isinstance(first["profile_catalog_digest"], str)
    # The full registry payload is embedded so an OLD run stays self-describing even
    # after the live registry is reweighted.
    assert [axis["key"] for axis in first["registry"]] == [axis.key for axis in AXES]
    assert {axis["role"] for axis in first["registry"]} <= {"headline", "candidate", "experimental"}


def test_registry_digest_changes_when_a_weight_moves() -> None:
    # The core property: a weight edit changes identity (no more silent re-scoring).
    base = [{"key": "k", "role": "headline", "weight": 0.5, "benches": ["a"], "legacy_benches": []}]
    moved = [{"key": "k", "role": "headline", "weight": 0.6, "benches": ["a"], "legacy_benches": []}]
    assert _digest(base) != _digest(moved)


def test_scorecard_id_binds_registry_scorers_and_ci_method() -> None:
    base = scorecard_identity()
    # Recompute the id with any one component perturbed -> must differ.
    for perturbation in (
        {"registry_digest": "0" * 64},
        {"scorer_versions": {**base["scorer_versions"], "mmlu_pro": "2"}},
        {"ci_method": "something-else"},
        {"scorecard_version": "9"},
        {"lane_spec_digest": "1" * 64},
        {"execution_profile_id": "gemma4_thinking_native_v1"},
        {"execution_profile_digest": "2" * 64},
    ):
        components = {
            "scorecard_version": base["scorecard_version"],
            "registry_digest": base["registry_digest"],
            "scorer_versions": base["scorer_versions"],
            "ci_method": base["ci_method"],
            "lane_spec_digest": base["lane_spec_digest"],
            "execution_profile_id": base["execution_profile_id"],
            "execution_profile_digest": base["execution_profile_digest"],
            **perturbation,
        }
        assert _digest(components) != base["scorecard_id"]


def test_scorecard_id_binds_selected_execution_profile() -> None:
    qwen = scorecard_identity("qwen_thinking_native_v1")
    gemma = scorecard_identity("gemma4_thinking_native_v1")

    assert qwen["execution_profile_id"] == "qwen_thinking_native_v1"
    assert gemma["execution_profile_id"] == "gemma4_thinking_native_v1"
    assert qwen["execution_profile"]["id"] == "qwen_thinking_native_v1"
    assert gemma["execution_profile"]["id"] == "gemma4_thinking_native_v1"
    assert qwen["scorecard_id"] != gemma["scorecard_id"]


def test_adding_registry_entry_does_not_change_selected_profile_scorecard_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = scorecard_identity("qwen_thinking_native_v1")
    synthetic = replace(
        QWEN_REASONING_ENTRY,
        id="synthetic_extra_native_v1",
        model_match=("synthetic-extra",),
    )

    monkeypatch.setattr(
        reasoning_registry,
        "REASONING_REGISTRY",
        (*reasoning_registry.REASONING_REGISTRY, synthetic),
    )
    extended = scorecard_identity("qwen_thinking_native_v1")

    assert extended["scorecard_id"] == base["scorecard_id"]
    assert extended["profile_catalog_digest"] != base["profile_catalog_digest"]


def test_profileless_scorecard_id_is_stable_and_distinct_from_profiled() -> None:
    answer_only = scorecard_identity()
    qwen = scorecard_identity("qwen_thinking_native_v1")

    assert answer_only == scorecard_identity()
    assert answer_only["execution_profile_id"] is None
    assert answer_only["execution_profile_digest"] is None
    assert answer_only["scorecard_id"] != qwen["scorecard_id"]


def test_every_registry_and_exec_bench_has_a_frozen_scorer_version() -> None:
    # Drift guard: identity can't silently omit a bench's scorer version.
    required = {bench for axis in AXES for bench in (*axis.benches, *axis.legacy_benches)}
    required |= set(EXEC_BENCHES)
    missing = required - set(SCORER_VERSIONS)
    assert not missing, f"benches missing a scorer version: {sorted(missing)}"

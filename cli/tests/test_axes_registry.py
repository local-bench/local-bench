from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.scoring.axes import (
    AXES,
    axis_membership,
    domain_weights,
    headline_displays,
    web_composite_weights,
    web_display_axes,
    web_source_bench_groups,
)
from localbench.scoring.metadata import BENCH_DOMAINS, DOMAIN_WEIGHTS

_SUITE_V1 = Path(__file__).resolve().parents[2] / "suite" / "v1" / "suite.json"


def test_headline_weights_sum_to_one_and_other_roles_are_zero() -> None:
    # Given the locked registry (METHODOLOGY-v1.2 §2-3).
    headline = [axis for axis in AXES if axis.role == "headline"]
    # Then only Knowledge + Instruction are headline, summing to 1.0.
    assert headline_displays() == ("Knowledge", "Instruction-Following")
    assert sum(axis.weight for axis in headline) == pytest.approx(1.0)
    assert all(axis.weight == 0.0 for axis in AXES if axis.role != "headline")


def test_domain_weights_and_bench_domains_are_derived_from_the_registry() -> None:
    # The runtime constants are derived, not a parallel hardcode.
    assert DOMAIN_WEIGHTS == domain_weights()
    assert DOMAIN_WEIGHTS["Knowledge"] == 0.5
    assert DOMAIN_WEIGHTS["Instruction-Following"] == 0.5
    assert DOMAIN_WEIGHTS["Math"] == 0.0
    assert DOMAIN_WEIGHTS["Long-Context"] == 0.0
    assert DOMAIN_WEIGHTS["Agentic"] == 0.0
    assert DOMAIN_WEIGHTS["Coding"] == 0.0
    # Every suite-v1 + legacy bench maps to its axis display label.
    assert BENCH_DOMAINS["mmlu_pro"] == "Knowledge"
    assert BENCH_DOMAINS["supergpqa"] == "Knowledge"
    assert BENCH_DOMAINS["ifbench"] == "Instruction-Following"
    assert BENCH_DOMAINS["ifeval"] == "Instruction-Following"
    assert BENCH_DOMAINS["olymmath_hard"] == "Math"
    assert BENCH_DOMAINS["amo"] == "Math"
    assert BENCH_DOMAINS["genmath"] == "Math"
    assert BENCH_DOMAINS["ruler_32k"] == "Long-Context"
    assert BENCH_DOMAINS["bfcl"] == "Agentic"
    assert BENCH_DOMAINS["bfcl_multi_turn"] == "Agentic"
    assert BENCH_DOMAINS["lcb"] == "Coding"


def test_web_derivations_track_the_registry() -> None:
    assert web_display_axes() == ("knowledge", "instruction", "math", "agentic")
    assert web_composite_weights() == {
        "knowledge": 0.5,
        "instruction": 0.5,
        "agentic": 0.0,
        "math": 0.0,
    }
    groups = web_source_bench_groups()
    # Suite-v1 benches are preferred over their v0 fallback (knowledge: mmlu_pro first).
    assert groups["knowledge"] == (("mmlu_pro",), ("supergpqa",))
    assert groups["instruction"] == (("ifbench",), ("ifeval",))
    assert groups["math"] == (("olymmath_hard", "amo"), ("genmath",))


def test_suite_v1_manifest_membership_matches_registry_drift_gate() -> None:
    # The drift gate: suite.json carries axis MEMBERSHIP only and must match the
    # single source of truth (compared order-independently, since axes pool items).
    manifest = json.loads(_SUITE_V1.read_text(encoding="utf-8"))
    manifest_axes = manifest["axes"]
    registry = axis_membership()
    assert set(manifest_axes) == set(registry)
    for axis, members in registry.items():
        assert set(manifest_axes[axis]["benches"]) == set(members), axis


def test_suite_v1_manifest_carries_no_weight_numbers() -> None:
    manifest = json.loads(_SUITE_V1.read_text(encoding="utf-8"))
    for axis, spec in manifest["axes"].items():
        assert "weight" not in spec, f"{axis} still hardcodes a weight in suite.json"

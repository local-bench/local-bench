from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.scoring.axes import (
    AXES,
    axis_membership,
    domain_weights,
    headline_displays,
    headline_web_axes,
    web_composite_weights,
    web_display_axes,
    web_source_bench_groups,
)
from localbench.scoring.benchmark_registry import BENCHMARK_MODULES, scored_default_benches
from localbench.scoring.metadata import BENCH_DOMAINS, DOMAIN_WEIGHTS

_SUITE_V1 = Path(__file__).resolve().parents[2] / "suite" / "v1" / "suite.json"


def test_headline_weights_sum_to_one_and_other_roles_are_zero() -> None:
    headline = [axis for axis in AXES if axis.role == "headline"]

    assert headline_displays() == (
        "Knowledge",
        "Instruction-Following",
        "Agentic",
        "Tool-calling",
        "Coding",
    )
    assert headline_web_axes() == ("knowledge", "instruction", "agentic", "tool_calling", "coding")
    assert sum(axis.weight for axis in headline) == pytest.approx(1.0)
    assert all(axis.weight == 0.0 for axis in AXES if axis.role != "headline")


def test_domain_weights_and_bench_domains_are_derived_from_the_registry() -> None:
    assert DOMAIN_WEIGHTS == domain_weights()
    assert DOMAIN_WEIGHTS["Knowledge"] == 0.15
    assert DOMAIN_WEIGHTS["Instruction-Following"] == 0.15
    assert DOMAIN_WEIGHTS["Math"] == 0.0
    assert DOMAIN_WEIGHTS["Long-Context"] == 0.0
    assert DOMAIN_WEIGHTS["Agentic"] == 0.50
    assert DOMAIN_WEIGHTS["Coding"] == 0.10
    assert DOMAIN_WEIGHTS["Tool-calling"] == 0.10
    assert BENCH_DOMAINS["mmlu_pro"] == "Knowledge"
    assert BENCH_DOMAINS["supergpqa"] == "Knowledge"
    assert BENCH_DOMAINS["ifbench"] == "Instruction-Following"
    assert BENCH_DOMAINS["ifeval"] == "Instruction-Following"
    assert BENCH_DOMAINS["olymmath_hard"] == "Math"
    assert BENCH_DOMAINS["amo"] == "Math"
    assert BENCH_DOMAINS["genmath"] == "Math"
    assert BENCH_DOMAINS["ruler_32k"] == "Long-Context"
    assert BENCH_DOMAINS["appworld_c"] == "Agentic"
    assert BENCH_DOMAINS["lcb"] == "Coding"
    assert BENCH_DOMAINS["tc_json_v1"] == "Tool-calling"


def test_web_derivations_track_the_registry() -> None:
    assert web_display_axes() == (
        "knowledge",
        "instruction",
        "math",
        "agentic",
        "tool_calling",
        "coding",
    )
    assert web_composite_weights() == {
        "knowledge": 0.15,
        "instruction": 0.15,
        "agentic": 0.50,
        "math": 0.0,
        "tool_calling": 0.10,
        "coding": 0.10,
    }
    groups = web_source_bench_groups()
    assert groups["knowledge"] == (("mmlu_pro",), ("supergpqa",))
    assert groups["instruction"] == (("ifbench",), ("ifeval",))
    assert groups["math"] == (("olymmath_hard", "amo"), ("genmath",))
    assert groups["agentic"] == (("appworld_c",),)
    assert groups["tool_calling"] == (("tc_json_v1",),)
    assert groups["coding"] == (("lcb",),)


def test_tool_calling_axis_is_weighted_headline_axis() -> None:
    axis = next(axis for axis in AXES if axis.key == "tool_calling")

    assert axis.display == "Tool-calling"
    assert axis.web_key == "tool_calling"
    assert axis.benches == ("tc_json_v1",)
    assert axis.legacy_benches == ()
    assert axis.role == "headline"
    assert axis.weight == 0.10
    assert axis.web_display is True


def test_coding_axis_is_weighted_lightweight_proxy() -> None:
    axis = next(axis for axis in AXES if axis.key == "coding")

    assert axis.display == "Coding"
    assert axis.web_key == "coding"
    assert axis.benches == ("lcb",)
    assert axis.legacy_benches == ()
    assert axis.role == "headline"
    assert axis.weight == 0.10
    assert axis.web_display is True


def test_benchmark_modules_define_fast_defaults_and_opt_in_expansions() -> None:
    assert [module.key for module in BENCHMARK_MODULES if module.role == "headline"] == [
        "core_text",
        "tool_calling",
        "coding",
        "agentic",
    ]
    assert scored_default_benches({"mmlu_pro", "ifbench", "tc_json_v1", "lcb"}) == (
        "mmlu_pro",
        "ifbench",
        "tc_json_v1",
        "lcb",
        "appworld_c",
    )
    assert scored_default_benches({"mmlu_pro", "ifbench", "tc_json_v1"}) == (
        "mmlu_pro",
        "ifbench",
        "tc_json_v1",
        "appworld_c",
    )
    coding = next(module for module in BENCHMARK_MODULES if module.key == "coding")
    assert coding.default_benches == ("lcb",)
    assert coding.opt_in_benches == ("bigcodebench_hard",)


def test_suite_v1_manifest_membership_matches_registry_drift_gate() -> None:
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

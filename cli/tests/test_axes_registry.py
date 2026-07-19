from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

import localbench.scoring.axes as axes_module

from localbench.scoring.axes import (
    AXES,
    FacetSpec,
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

_SUITE_V2 = Path(__file__).resolve().parents[2] / "suite" / "v2" / "suite.json"


def test_headline_weights_sum_to_one_and_other_roles_are_zero() -> None:
    headline = [axis for axis in AXES if axis.role == "headline"]

    assert headline_displays() == (
        "Knowledge",
        "Instruction-Following",
        "Math",
        "Agentic",
        "Coding",
    )
    assert headline_web_axes() == (
        "knowledge",
        "instruction",
        "math",
        "tool_use",
        "coding",
    )
    assert sum(axis.weight for axis in headline) == pytest.approx(1.0)
    assert all(axis.weight == 0.0 for axis in AXES if axis.role != "headline")


def test_domain_weights_and_bench_domains_are_derived_from_the_registry() -> None:
    assert DOMAIN_WEIGHTS == domain_weights()
    assert DOMAIN_WEIGHTS["Knowledge"] == 0.225
    assert DOMAIN_WEIGHTS["Instruction-Following"] == 0.225
    assert DOMAIN_WEIGHTS["Math"] == 0.075
    assert DOMAIN_WEIGHTS["Long-Context"] == 0.0
    assert DOMAIN_WEIGHTS["Agentic"] == 0.25
    assert DOMAIN_WEIGHTS["Coding"] == 0.225
    assert BENCH_DOMAINS["mmlu_pro"] == "Knowledge"
    assert BENCH_DOMAINS["supergpqa"] == "Knowledge"
    assert BENCH_DOMAINS["ifbench"] == "Instruction-Following"
    assert BENCH_DOMAINS["ifeval"] == "Instruction-Following"
    assert BENCH_DOMAINS["olymmath_hard"] == "Math"
    assert BENCH_DOMAINS["amo"] == "Math"
    assert BENCH_DOMAINS["genmath"] == "Math"
    assert BENCH_DOMAINS["ruler_32k"] == "Long-Context"
    assert BENCH_DOMAINS["appworld_c"] == "Agentic"
    assert BENCH_DOMAINS["bfcl_multi_turn_base"] == "BFCL v3 Multi-Turn Base (frozen snapshot)"
    assert BENCH_DOMAINS["bigcodebench_hard"] == "Coding"
    assert BENCH_DOMAINS["lcb"] == "Coding"
    assert BENCH_DOMAINS["tc_json_v1"] == "Call Formatting"
    assert BENCH_DOMAINS["bfcl"] == "BFCL Single-Turn"
    assert BENCH_DOMAINS["bfcl_multi_turn_long_context"] == "BFCL Multi-Turn Long-Context"


def test_web_derivations_track_the_registry() -> None:
    assert web_display_axes() == (
        "knowledge",
        "instruction",
        "math",
        "tool_use",
        "coding",
    )
    assert web_composite_weights() == {
        "knowledge": 0.225,
        "instruction": 0.225,
        "tool_use": 0.25,
        "math": 0.075,
        "coding": 0.225,
    }
    groups = web_source_bench_groups()
    assert groups["knowledge"] == (("mmlu_pro",), ("supergpqa",))
    assert groups["instruction"] == (("ifbench",), ("ifeval",))
    assert groups["math"] == (("olymmath_hard", "amo"), ("genmath",))
    assert groups["tool_use"] == (("appworld_c",),)
    assert groups["coding"] == (("bigcodebench_hard",), ("lcb",))


def test_tool_use_axis_declares_appworld_only_facet() -> None:
    axis = next(axis for axis in AXES if axis.key == "tool_use")

    assert axis.display == "Agentic"
    assert axis.web_key == "tool_use"
    assert axis.benches == ("appworld_c",)
    assert axis.legacy_benches == ()
    assert axis.role == "headline"
    assert axis.weight == 0.25
    assert axis.web_display is True
    assert axis.facets == (FacetSpec("agentic", "appworld_c", 1.0),)


def test_diagnostics_are_experimental_and_unweighted() -> None:
    diagnostics = [axis for axis in AXES if axis.role == "experimental"]

    assert {axis.benches for axis in diagnostics} == {
        ("tc_json_v1",),
        ("bfcl",),
        ("bfcl_multi_turn_base",),
        ("bfcl_multi_turn_long_context",),
    }
    assert all(axis.weight == 0.0 and not axis.web_display for axis in diagnostics)
    assert all("bfcl_multi_turn" not in axis.benches for axis in AXES)


@pytest.mark.parametrize(
    ("facets", "message"),
    (
        (
            (FacetSpec("duplicate", "appworld_c", 0.5), FacetSpec("duplicate", "tc_json_v1", 0.5)),
            "facet keys must be unique",
        ),
        (
            (FacetSpec("agentic", "appworld_c", 1.0), FacetSpec("format", "tc_json_v1", 0.0)),
            "facet weights must be positive",
        ),
        (
            (FacetSpec("agentic", "appworld_c", 0.5), FacetSpec("format", "tc_json_v1", 0.4)),
            "facet weights must sum to 1.0",
        ),
        (
            (FacetSpec("unknown", "not_on_axis", 1.0),),
            "facet benches must belong",
        ),
    ),
)
def test_registry_validation_rejects_invalid_facets(
    monkeypatch: pytest.MonkeyPatch,
    facets: tuple[FacetSpec, ...],
    message: str,
) -> None:
    invalid = tuple(
        replace(axis, facets=facets) if axis.key == "tool_use" else axis
        for axis in AXES
    )
    monkeypatch.setattr(axes_module, "AXES", invalid)

    with pytest.raises(ValueError, match=message):
        axes_module._validate()


def test_coding_axis_is_weighted_execution_axis_with_legacy_proxy() -> None:
    axis = next(axis for axis in AXES if axis.key == "coding")

    assert axis.display == "Coding"
    assert axis.web_key == "coding"
    assert axis.benches == ("bigcodebench_hard",)
    assert axis.legacy_benches == ("lcb",)
    assert axis.role == "headline"
    assert axis.weight == 0.225
    assert axis.web_display is True


def test_benchmark_modules_define_fast_defaults_and_opt_in_expansions() -> None:
    assert [module.key for module in BENCHMARK_MODULES if module.role == "headline"] == [
        "core_text",
        "math",
        "tool_calling",
        "coding",
        "agentic",
    ]
    assert scored_default_benches(
        {"mmlu_pro", "ifbench", "olymmath_hard", "amo", "tc_json_v1", "bigcodebench_hard"},
    ) == (
        "mmlu_pro",
        "ifbench",
        "olymmath_hard",
        "amo",
        "tc_json_v1",
        "bigcodebench_hard",
        "appworld_c",
    )
    assert scored_default_benches() == (
        "mmlu_pro",
        "ifbench",
        "olymmath_hard",
        "amo",
        "tc_json_v1",
        "bfcl_multi_turn_base",
        "bigcodebench_hard",
        "appworld_c",
    )
    tool_calling = next(module for module in BENCHMARK_MODULES if module.key == "tool_calling")
    assert tool_calling.default_benches == ("tc_json_v1", "bfcl_multi_turn_base")
    assert tool_calling.opt_in_benches == ("bfcl_multi_turn_long_context", "bfcl")
    assert tool_calling.lane == "http"
    coding = next(module for module in BENCHMARK_MODULES if module.key == "coding")
    assert coding.default_benches == ("bigcodebench_hard",)
    assert coding.opt_in_benches == ("lcb",)


def test_suite_v2_manifest_membership_matches_registry_drift_gate() -> None:
    manifest = json.loads(_SUITE_V2.read_text(encoding="utf-8"))
    manifest_axes = manifest["axes"]
    registry = axis_membership()
    # The suite identity is immutable: its original tool_use coverage bucket still
    # contains tc_json_v1 and BFCL base even though both are live diagnostics.
    assert set(manifest_axes) == set(registry) - {
        "call_formatting",
        "bfcl_multi_turn_base",
    }
    for axis, members in registry.items():
        if axis == "call_formatting":
            assert set(members) == {"tc_json_v1"}
        elif axis == "bfcl_multi_turn_base":
            assert set(members) == {"bfcl_multi_turn_base"}
        elif axis == "tool_use":
            assert set(manifest_axes[axis]["benches"]) == set(members) | {
                "tc_json_v1",
                "bfcl_multi_turn_base",
            }
        else:
            assert set(manifest_axes[axis]["benches"]) == set(members), axis


def test_suite_v2_manifest_carries_no_weight_numbers() -> None:
    manifest = json.loads(_SUITE_V2.read_text(encoding="utf-8"))
    for axis, spec in manifest["axes"].items():
        assert "weight" not in spec, f"{axis} still hardcodes a weight in suite.json"

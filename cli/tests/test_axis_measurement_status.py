from __future__ import annotations

import pytest

from localbench._scoring import BenchAggregate, composite
from localbench.scoring.axis_status import (
    axis_status_for_benches,
    mark_axis_not_measured,
    not_measured_axis,
    parse_axis_status,
    parse_axis_status_block,
    serialize_axis_status,
)


def test_composite_when_axis_not_measured_excludes_weight_instead_of_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given three measured axes and a fourth weighted axis with a carried aggregate
    # that must not enter the score because measurement failed.
    monkeypatch.setattr(
        "localbench._scoring.DOMAIN_WEIGHTS",
        {
            "Knowledge": 0.10,
            "Instruction-Following": 0.20,
            "Math": 0.30,
            "Agentic": 0.40,
        },
    )
    benches = {
        "mmlu_pro": _aggregate(0.20),
        "ifbench": _aggregate(0.50),
        "genmath": _aggregate(0.80),
        "appworld_c": _aggregate(0.0),
    }
    status = axis_status_for_benches(benches)
    mark_axis_not_measured(
        status,
        "agentic",
        reason="sandbox_unavailable",
        detail="bubblewrap is unavailable",
    )

    # When the composite is computed with the measurement-status contract.
    result = composite(benches, axis_status=status)

    # Then the unavailable axis contributes neither score nor denominator weight.
    expected = ((0.10 * 0.20) + (0.20 * 0.50) + (0.30 * 0.80)) / 0.60
    zero_included = ((0.10 * 0.20) + (0.20 * 0.50) + (0.30 * 0.80)) / 1.00
    assert result == pytest.approx(expected)
    assert result != pytest.approx(zero_included)


def test_axis_status_reason_codes_round_trip_through_serialization() -> None:
    # Given a not-measured axis status with an optional human detail.
    status = not_measured_axis(
        "agentic",
        reason="scorer_unavailable",
        detail="BFCL evaluator is not installed",
    )
    block = axis_status_for_benches(("mmlu_pro", "ifbench"))
    mark_axis_not_measured(
        block,
        "agentic",
        reason="scorer_unavailable",
        detail="BFCL evaluator is not installed",
    )

    # When serializing and parsing the status payloads.
    parsed_status = parse_axis_status(serialize_axis_status(status))
    parsed_block = parse_axis_status_block(block)

    # Then reason codes and detail survive exactly.
    assert parsed_status == status
    assert parsed_block == block


def test_composite_when_all_axes_measured_matches_legacy_call_exactly() -> None:
    # Given the same all-measured bench aggregates the legacy composite accepted.
    benches = {
        "mmlu_pro": _aggregate(0.25, n=2),
        "ifbench": _aggregate(0.75, n=2),
        "appworld_c": _aggregate(0.50, n=2),
    }
    status = axis_status_for_benches(benches)

    # When computing with and without the additive status block.
    legacy = composite(benches)
    with_status = composite(benches, axis_status=status)

    # Then the float value is bit-identical for a clean all-measured run.
    assert with_status.hex() == legacy.hex()


def test_composite_when_suite_axes_override_registry_axis_uses_suite_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a suite override that scores mmlu_pro under a weighted suite-only axis
    # while its registry knowledge axis is not measured in the same status block.
    monkeypatch.setattr(
        "localbench._scoring.DOMAIN_WEIGHTS",
        {
            "Knowledge": 0.90,
            "Instruction-Following": 0.000000000001,
        },
    )
    suite_axes = {"suite_knowledge": {"benches": ["mmlu_pro"]}}
    benches = {
        "mmlu_pro": _aggregate(0.90),
        "ifbench": _aggregate(0.10),
    }
    status = axis_status_for_benches(("ifbench", "mmlu_pro"), suite_axes)
    mark_axis_not_measured(status, "knowledge", reason="not_run")

    # When computing the composite with the suite-aware status contract.
    result = composite(benches, axis_status=status, suite_axes=suite_axes)

    # Then the measured mmlu_pro aggregate remains included via suite_knowledge.
    assert result == pytest.approx(0.90)


def _aggregate(score: float, *, n: int = 1) -> BenchAggregate:
    return {
        "n": n,
        "n_errors": 0,
        "n_extraction_failures": 0,
        "raw_accuracy": score,
        "chance_corrected": score,
        "termination_rate": 1.0,
        "conditional_accuracy": score,
    }

from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench._scoring import BenchAggregate
from localbench._types import JsonObject
from localbench.scoring.axis_status import axis_status_for_benches
from localbench.submissions.canon import canonical_json_bytes, sha256_bytes
from localbench.submissions.foundation import (
    migrate_accepted_result_projection_v1,
    validate_accepted_result_projection,
)
from localbench.submissions.foundation_scores import axis_projection, projection_score_summary
from localbench.submissions.projection import projection_object_sha256
from localbench.submissions.validate import SubmissionValidationError

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> dict[str, object]:
    value = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_golden_v1_to_v2_migration_is_exact_and_valid() -> None:
    migrated = migrate_accepted_result_projection_v1(_fixture("accepted_projection_v1_golden.json"))
    assert migrated == _fixture("accepted_projection_v2_golden.json")
    validate_accepted_result_projection(migrated)


def test_object_hash_and_semantic_hash_are_explicitly_distinct_domains() -> None:
    projection = _fixture("accepted_projection_v2_golden.json")
    object_hash = projection_object_sha256(projection)
    assert object_hash == sha256_bytes(canonical_json_bytes(projection))
    assert object_hash != projection["artifact_hashes"]["projection_sha256"]  # type: ignore[index]


def test_v2_schema_accepts_submitter_side_client_reported_projection() -> None:
    projection = _fixture("accepted_projection_v2_golden.json")
    projection["verification_level"] = "client_reported"

    validate_accepted_result_projection(projection)


def test_full_exec_projection_uses_canonical_axes_as_composite_inputs() -> None:
    benches = {
        "mmlu_pro": _aggregate(raw_accuracy=0.8, chance_corrected=0.6),
        "ifbench": _aggregate(raw_accuracy=0.7, chance_corrected=0.5),
        "olymmath_hard": _aggregate(raw_accuracy=0.4, chance_corrected=0.3),
        "amo": _aggregate(raw_accuracy=0.2, chance_corrected=0.1),
        "appworld_c": _aggregate(raw_accuracy=0.6, chance_corrected=0.6),
        "bigcodebench_hard": _aggregate(raw_accuracy=0.9, chance_corrected=0.4),
        "tc_json_v1": _aggregate(raw_accuracy=0.75, chance_corrected=0.7),
    }
    suite_axes = {
        "knowledge": {"benches": ["mmlu_pro"]},
        "instruction_following": {"benches": ["ifbench"]},
        "math": {"benches": ["olymmath_hard", "amo"]},
        "agentic": {"benches": ["appworld_c"]},
        "coding": {"benches": ["bigcodebench_hard"]},
        "tool_calling": {"benches": ["tc_json_v1"]},
        "long_context": {"benches": ["ruler_32k"]},
    }
    status = axis_status_for_benches(benches, suite_axes)

    axes = axis_projection(
        benches,
        status,
        coverage_profile_id="full-exec-6axis-v1",
        suite_axes=suite_axes,
    )
    summary = projection_score_summary(
        benches,
        status,
        suite_axes=suite_axes,
        coverage_profile_id="full-exec-6axis-v1",
    )

    assert set(axes) == set(suite_axes)
    assert axes["agentic"]["score"] == 0.6
    assert axes["tool_calling"]["score"] == 0.7
    assert axes["coding"]["score"] == 0.4
    assert "tool_use" not in axes
    assert "call_formatting" not in axes
    assert summary["headline_score"] == _weighted_sum(axes)
    assert summary["partial_composite"] == _weighted_sum(axes)


@pytest.mark.parametrize("mutation", ["extra", "nan", "digest", "suite_pair"])
def test_v2_schema_fails_closed_on_adversarial_contract_mutations(mutation: str) -> None:
    projection = _fixture("accepted_projection_v2_golden.json")
    if mutation == "extra":
        projection["model"]["catalog_slug"] = "protected"  # type: ignore[index]
    elif mutation == "nan":
        projection["scores"]["partial_composite"] = float("nan")  # type: ignore[index]
    elif mutation == "digest":
        projection["artifact_hashes"]["bundle_sha256"] = "BAD"  # type: ignore[index]
    else:
        projection["suite_manifest_sha256"] = "0" * 64
    with pytest.raises(SubmissionValidationError, match="accepted projection invalid"):
        validate_accepted_result_projection(projection)


def _aggregate(*, raw_accuracy: float, chance_corrected: float) -> BenchAggregate:
    return {
        "n": 1,
        "n_errors": 0,
        "n_extraction_failures": 0,
        "raw_accuracy": raw_accuracy,
        "chance_corrected": chance_corrected,
        "termination_rate": 1.0,
        "conditional_accuracy": raw_accuracy,
    }


def _weighted_sum(axes: JsonObject) -> float:
    weights = {
        "knowledge": 0.225,
        "instruction_following": 0.225,
        "math": 0.075,
        "agentic": 0.25,
        "coding": 0.225,
        "tool_calling": 0.0,
    }
    return round(
        sum(
            weight * float(_axis(axes, axis)["score"])
            for axis, weight in weights.items()
        ),
        4,
    )


def _axis(axes: JsonObject, name: str) -> JsonObject:
    value = axes[name]
    assert isinstance(value, dict)
    return value

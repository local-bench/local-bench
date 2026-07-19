from __future__ import annotations

import json
from pathlib import Path

import pytest

from board_fixtures import run_record
from localbench.scoring.comparison_guard import lineage_composite_delta
from localbench.scoring.editorial import (
    INDEX_VERSION_V3,
    INDEX_VERSION_V4,
    index_version_for_benches,
    index_version_for_coverage_profile,
)
from localbench.scoring.paired_delta import compare_runs
from localbench.scoring.season2_rescore import rescore_record_season2
from localbench.scoring.season_bridge import build_bridge_entry, write_bridge_artifact


def test_editorial_label_is_keyed_by_coverage_profile_identity() -> None:
    assert (
        index_version_for_coverage_profile("full-exec-tooluse-5axis-v2")
        == INDEX_VERSION_V4
    )
    assert index_version_for_coverage_profile("full-exec-6axis-v1") == INDEX_VERSION_V4
    assert (
        index_version_for_coverage_profile("static-exec-5axis-v1") == INDEX_VERSION_V3
    )


def test_editorial_label_maps_complete_six_axis_benches_to_current_index() -> None:
    benches = {
        "mmlu_pro",
        "ifbench",
        "tc_json_v1",
        "bigcodebench_hard",
        "olymmath_hard",
        "amo",
        "appworld_c",
    }

    assert index_version_for_benches(benches) == INDEX_VERSION_V4


def test_season2_rescore_complete_record_emits_v4_strict_composite_and_facets() -> None:
    record = run_record(
        bigcode_correct=(True, False), math_correct=(True, False), lcb_correct=None
    )
    record["index_version"] = INDEX_VERSION_V3
    record["model"] = {"file_sha256": "a" * 64, "quant_label": "Q4_K_M"}

    rescored = rescore_record_season2(record, bootstrap_iters=50)

    assert rescored["index_version"] == INDEX_VERSION_V4
    assert rescored["coverage_profile_id"] == "full-exec-tooluse-5axis-v2"
    assert rescored["missing_headline_axes"] == []
    assert rescored["composite_v4"] is not None
    assert set(rescored["axes"]["tool_use"]["facets"]) == {  # type: ignore[index]
        "agentic",
        "multi_turn_tool_control",
    }


def test_season2_rescore_missing_tool_facet_omits_tool_use_and_strict_composite() -> (
    None
):
    record = run_record(
        bfcl_base_correct=None,
        bigcode_correct=(True, False),
        math_correct=(True, False),
        lcb_correct=None,
    )
    record["index_version"] = INDEX_VERSION_V3
    record["model"] = {"file_sha256": "a" * 64}

    rescored = rescore_record_season2(record, bootstrap_iters=25)

    assert "tool_use" not in rescored["axes"]
    assert rescored["missing_headline_axes"] == ["tool_use"]
    assert rescored["composite_v4"] is None


def test_bridge_entry_maps_old_agentic_and_tool_calling_to_tool_use_facets() -> None:
    season_1, season_2 = _bridge_pair()

    entry = build_bridge_entry(season_1, season_2)

    assert entry["season_1"]["composite_v3"]["point_raw"] == 0.6  # type: ignore[index]
    assert entry["season_2"]["composite_v4"]["point_raw"] == 0.7  # type: ignore[index]
    mapping = entry["axis_mapping"]
    assert [(row["season_1_axis"], row["season_2_facet"]) for row in mapping] == [  # type: ignore[index]
        ("agentic", "agentic"),
        (None, "multi_turn_tool_control"),
        ("tool_calling", "call_formatting"),
    ]
    assert entry["per_axis_deltas"]["knowledge"]["delta"] == pytest.approx(0.1)  # type: ignore[index]


def test_bridge_artifact_bytes_are_deterministic_under_runs_board(
    tmp_path: Path,
) -> None:
    season_1, season_2 = _bridge_pair()
    out = tmp_path / "runs" / "board" / "season-1-to-2-bridge.json"

    first = write_bridge_artifact([(season_1, season_2)], output_path=out)
    first_bytes = out.read_bytes()
    second = write_bridge_artifact([(season_1, season_2)], output_path=out)

    assert first == second == json.loads(first_bytes)
    assert out.read_bytes() == first_bytes
    assert first["schema_version"] == "localbench.season_bridge.v1"


def test_composite_guards_reject_cross_season_but_allow_same_season_lineage() -> None:
    base = {"index_version": INDEX_VERSION_V3, "composite": {"point_raw": 0.5}}
    tune = {"index_version": INDEX_VERSION_V3, "composite": {"point_raw": 0.6}}
    assert lineage_composite_delta(tune, base) == pytest.approx(0.1)
    with pytest.raises(ValueError, match="matching index_version"):
        lineage_composite_delta({**tune, "index_version": INDEX_VERSION_V4}, base)


def test_paired_delta_rejects_mixed_or_missing_editorial_labels() -> None:
    item = {"id": "x", "bench": "ifbench", "correct": True}
    season_1 = {"index_version": INDEX_VERSION_V3, "items": [item]}
    season_2 = {"index_version": INDEX_VERSION_V4, "items": [item]}
    with pytest.raises(ValueError, match="matching index_version"):
        compare_runs(season_1, season_2, iters=5)
    with pytest.raises(ValueError, match="must carry"):
        compare_runs({"items": [item]}, {"items": [item]}, iters=5)


def _bridge_pair() -> tuple[dict, dict]:
    identity = {"file_sha256": "a" * 64, "quant_label": "Q4_K_M"}
    season_1 = {
        "model_identity": identity,
        "index_version": INDEX_VERSION_V3,
        "composite": {"point_raw": 0.6},
        "axes": {
            "knowledge": {"point_raw": 0.5},
            "agentic": {"point_raw": 0.4},
            "tool_calling": {"point_raw": 0.6},
        },
    }
    season_2 = {
        "model_identity": identity,
        "index_version": INDEX_VERSION_V4,
        "composite_v4": {"point_raw": 0.7},
        "axes": {
            "knowledge": {"point_raw": 0.6},
            "tool_use": {
                "point_raw": 0.55,
                "facets": {
                    "agentic": {"point_raw": 0.5},
                    "multi_turn_tool_control": {"point_raw": 0.4},
                    "call_formatting": {"point_raw": 0.7},
                },
            },
        },
    }
    return season_1, season_2

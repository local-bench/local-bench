from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import localbench.facet_backfill as facet_backfill_module
from localbench._suite import read_json_object, render_benches
from localbench.facet_backfill import FacetBackfillError, compose_facet_backfill
from localbench.scoring.scorecard import scorecard_identity
from localbench.scoring.season2_rescore import rescore_record_season2
from localbench.suite_release import (
    build_suite_release_manifest,
    coverage_profile_for_id,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUITE_V1 = _REPO_ROOT / "suite" / "v1"
_SUITE_V2 = _REPO_ROOT / "suite" / "v2"
_PROFILE = "generic_think_tags_8192_v1"
_LANE = "bounded-final-v2"
_MODEL_SHA = "a" * 64
_MODEL_SIZE = 123_456_789
_V1_SHAS = {
    "full-exec-6axis-v1": "c4098df81440c4489ee8c6d6967f3a5d6f9d6941810779abd135326ad734f468",
    "static-exec-5axis-v1": "4e240f8cffe8826ef1fd723f54b4b789d93990851d838818bce0954a38c61d64",
    "static-core-diag-v1": "f2f8c9a67df3adea5cec463fc156ccae073ea9deb54d4487d72b9826fe385c69",
}


def test_corrected_v2_profile_requires_1361_static_plus_96_agentic_items() -> None:
    profile = coverage_profile_for_id("full-exec-tooluse-5axis-v2")
    assert set(profile.benches) == {
        "mmlu_pro",
        "ifbench",
        "olymmath_hard",
        "amo",
        "appworld_c",
        "bfcl_multi_turn_base",
        "tc_json_v1",
        "bigcodebench_hard",
    }
    suite = read_json_object(_SUITE_V2 / "suite.json")
    static = [bench for bench in profile.benches if bench != "appworld_c"]
    rendered = render_benches(",".join(static), "standard", None, _SUITE_V2, suite, [])
    assert sum(len(bench.benchmark_items) for bench in rendered) == 1_361
    assert 1_361 + 96 == 1_457


def test_composer_happy_path_passes_coverage_rescore_and_preserves_original(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_path, partial_dir, out_path = _campaign_files(tmp_path)
    before = original_path.read_bytes()
    monkeypatch.setattr(
        facet_backfill_module,
        "rescore_record_season2",
        lambda record: rescore_record_season2(record, bootstrap_iters=25),
    )

    result = compose_facet_backfill(original_path, partial_dir, out_path)

    assert original_path.read_bytes() == before
    assert out_path.is_file()
    assert len(result["items"]) == 1_457
    assert result["index_version"] == "index-v4.0"
    assert result["season2_rescore"]["missing_headline_axes"] == []
    assert result["season2_rescore"]["composite_v4"] is not None
    assert set(result["season2_rescore"]["axes"]["tool_use"]["facets"]) == {
        "agentic",
        "multi_turn_tool_control",
    }
    assert result["facet_backfill"]["attached_item_count"] == 50
    assert result["facet_backfill"]["partial_campaign_status"]["completeness_check"] == (
        "complete-and-exact-item-count"
    )
    for audit_name in ("budget_audit", "prompt_audit", "sampler_audit"):
        assert set(result[audit_name]["campaigns"]) == {"original", "partial"}
    attached = [item for item in result["items"] if item["bench"] == "bfcl_multi_turn_base"]
    assert all(item["facet_backfill_campaign"]["campaign_id"] for item in attached)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("sha", "model file_sha256"),
        ("size", "model file_size_bytes"),
        ("profile_id", "execution profile"),
        ("profile_digest", "execution profile"),
        ("lane", "lane_spec_id"),
        ("renderer", "prompt_renderer"),
        ("temperature", "sampler pins"),
        ("top_k", "sampler pins"),
        ("seed", "sampler pins"),
        ("policy", "sampler pins"),
        ("single_slot", "single-slot"),
    ],
)
def test_composer_refuses_identity_and_audit_mismatches(
    tmp_path: Path,
    mutation: str,
    match: str,
) -> None:
    original_path, partial_dir, out_path = _campaign_files(tmp_path)
    partial_path = partial_dir / "localbench-run.json"
    partial = _read(partial_path)
    if mutation == "sha":
        partial["model"]["file_sha256"] = "b" * 64
        partial["manifest"]["model"]["file_sha256"] = "b" * 64
    elif mutation == "size":
        partial["manifest"]["model"]["file_size_bytes"] += 1
    elif mutation == "profile_id":
        partial["manifest"]["scorecard"]["execution_profile_id"] = "gemma4_channel_8192_v1"
        partial["manifest"]["execution_profile"]["id"] = "gemma4_channel_8192_v1"
        partial["manifest"]["sampling"]["execution_profile_id"] = "gemma4_channel_8192_v1"
    elif mutation == "profile_digest":
        partial["manifest"]["scorecard"]["execution_profile_digest"] = "b" * 64
        partial["manifest"]["execution_profile"]["digest"] = "b" * 64
    elif mutation == "lane":
        partial["manifest"]["scorecard"]["lane_spec_id"] = "bounded-final-v1"
        partial["manifest"]["suite"]["lane"] = "bounded-final-v1"
    elif mutation == "renderer":
        partial["manifest"]["prompt_renderer"]["chat_template_sha256"] = "b" * 64
    elif mutation == "temperature":
        partial["sampler_audit"]["temperature"] = 0.5
    elif mutation == "top_k":
        partial["sampler_audit"]["top_k"] = 2
    elif mutation == "seed":
        partial["sampler_audit"]["seed"] = 999
    elif mutation == "policy":
        partial["sampler_audit"]["determinism_policy"] = "different-policy"
    elif mutation == "single_slot":
        partial["manifest"]["runtime"]["parallel_slots"] = 2
    _write(partial_path, partial)

    with pytest.raises(FacetBackfillError, match=match):
        compose_facet_backfill(original_path, partial_dir, out_path)
    assert not out_path.exists()


@pytest.mark.parametrize(
    "mutation", ["duplicate", "missing", "wrong", "duplicate_original", "missing_verdict"]
)
def test_composer_refuses_duplicate_missing_and_wrong_item_ids(
    tmp_path: Path,
    mutation: str,
) -> None:
    original_path, partial_dir, out_path = _campaign_files(tmp_path)
    partial_path = partial_dir / "localbench-run.json"
    partial = _read(partial_path)
    if mutation == "duplicate":
        partial["items"][-1] = copy.deepcopy(partial["items"][0])
    elif mutation == "missing":
        partial["items"].pop()
    elif mutation == "wrong":
        partial["items"][-1]["id"] = "not-a-frozen-item"
    elif mutation == "missing_verdict":
        partial["items"][-1].pop("correct")
    else:
        original = _read(original_path)
        original["items"].append(copy.deepcopy(partial["items"][0]))
        _write(original_path, original)
    _write(partial_path, partial)

    with pytest.raises(FacetBackfillError, match="duplicate|exactly|verdict"):
        compose_facet_backfill(original_path, partial_dir, out_path)
    assert not out_path.exists()


def test_composer_refuses_incomplete_partial_status(tmp_path: Path) -> None:
    original_path, partial_dir, out_path = _campaign_files(tmp_path)
    _write(
        partial_dir / "run.status.json",
        {"state": "running", "completed_items": 49, "total_items": 50},
    )

    with pytest.raises(FacetBackfillError, match="status must be complete"):
        compose_facet_backfill(original_path, partial_dir, out_path)
    assert not out_path.exists()


def test_three_frozen_v1_manifest_shas_are_byte_unchanged() -> None:
    actual = {
        profile: build_suite_release_manifest(_SUITE_V1, coverage_profile_id=profile)[
            "suite_manifest_sha256"
        ]
        for profile in _V1_SHAS
    }
    print(actual)
    assert actual == _V1_SHAS


def _campaign_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    partial_dir = tmp_path / "partial"
    partial_dir.mkdir()
    original_path = tmp_path / "original.json"
    out_path = tmp_path / "composed.json"
    original, partial = _records()
    _write(original_path, original)
    _write(partial_dir / "localbench-run.json", partial)
    _write(
        partial_dir / "run.status.json",
        {"state": "complete", "completed_items": 50, "total_items": 50},
    )
    return original_path, partial_dir, out_path


def _records() -> tuple[dict, dict]:
    suite = read_json_object(_SUITE_V2 / "suite.json")
    original_benches = (
        "mmlu_pro",
        "ifbench",
        "olymmath_hard",
        "amo",
        "tc_json_v1",
        "bigcodebench_hard",
    )
    original_rendered = render_benches(",".join(original_benches), "standard", None, _SUITE_V2, suite, [])
    partial_rendered = render_benches("bfcl_multi_turn_base", "standard", None, _SUITE_V2, suite, [])
    original_items = [
        _scored_item(bench.name, str(item["id"]))
        for bench in original_rendered
        for item in bench.benchmark_items
    ]
    original_items.extend(_scored_item("appworld_c", f"appworld-{index:03d}") for index in range(96))
    partial_items = [
        _scored_item(bench.name, str(item["id"]))
        for bench in partial_rendered
        for item in bench.benchmark_items
    ]
    original = _record(original_items, "2026-07-01T00:00:00Z", "2026-07-02T00:00:00Z")
    original["agentic_run"] = {"subset_size": 96, "mean_asr": 0.5}
    original["index_version"] = "index-v3.0"
    partial = _record(partial_items, "2026-07-03T00:00:00Z", "2026-07-03T01:00:00Z")
    return original, partial


def _record(items: list[dict], started: str, finished: str) -> dict:
    scorecard = scorecard_identity(_PROFILE, lane_spec_id=_LANE)
    benches = sorted({str(item["bench"]) for item in items})
    policy = {
        "policy_id": "gpu-greedy-single-slot-v1",
        "client": {"temperature": 0, "top_k": 1, "seed": 1234, "concurrency": 1},
        "server": {"parallel_slots": 1, "continuous_batching": False},
    }
    return {
        "schema_version": "localbench-result-bundle-v0.1",
        "run_started_at": started,
        "run_finished_at": finished,
        "model": {"name": "fixture-model", "file_sha256": _MODEL_SHA},
        "manifest": {
            "suite": {
                "suite_version": "suite-v1",
                "suite_release_id": "suite-v1-full-exec-6axis-v1",
                "coverage_profile_id": "full-exec-6axis-v1",
                "tier": "standard",
                "lane": _LANE,
            },
            "scorecard": scorecard,
            "execution_profile": {
                "id": _PROFILE,
                "digest": scorecard["execution_profile_digest"],
            },
            "model": {
                "file_sha256": _MODEL_SHA,
                "file_size_bytes": _MODEL_SIZE,
                "family": "qwen35",
                "quant_label": "Q4_K_M",
            },
            "prompt_renderer": {
                "source": "hf-chat-template",
                "hf_model_id": "Qwen/Qwen3.6-27B",
                "chat_template_sha256": "c" * 64,
                "answer_stop": ["<|im_end|>"],
                "template_kwargs": {"enable_thinking": True},
            },
            "runtime": {"parallel_slots": 1},
            "execution": {"concurrency": 1, "started_at": started, "finished_at": finished},
            "sampling": {
                "temperature": 0.0,
                "top_k": 1,
                "seed": 1234,
                "determinism_policy": policy,
                "execution_profile_id": _PROFILE,
                "by_bench": {
                    bench: {"temperature": 0.0, "top_k": 1, "seed": 1234, "max_tokens": 16}
                    for bench in benches
                },
            },
        },
        "items": items,
        "benches": {},
        "totals": {"wall_time_seconds": 1.0},
        "conformance": {},
        "prompt_audit": {
            "status": "canonical",
            "execution_profile_id": _PROFILE,
            "user_supplied_stops_removed": False,
        },
        "sampler_audit": {
            "status": "deterministic",
            "temperature": 0.0,
            "top_k": 1,
            "seed": 1234,
            "determinism_policy": "gpu-greedy-single-slot-v1",
        },
    }


def _scored_item(bench: str, item_id: str) -> dict:
    return {
        "bench": bench,
        "id": item_id,
        "correct": True,
        "error": None,
        "finish_reason": "stop",
        "response_text": "fixture response",
        "extracted": "fixture",
        "max_tokens": 16,
        "generated_tokens": {"total": 1},
        "latency_seconds": 0.01,
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

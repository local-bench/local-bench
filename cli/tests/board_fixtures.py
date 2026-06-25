from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TypeAlias

from localbench.scoring.axes import web_composite_weights
from localbench.scoring.signed_score import chance_for_bench, signed_score

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

FROZEN_AT = "2026-06-23T00:00:00+00:00"


def write_inputs(tmp_path: Path, sources: list[JsonObject]) -> dict[str, Path]:
    runs = tmp_path / "runs"
    runs.mkdir()
    curation = tmp_path / "curation.json"
    curation.write_text(json.dumps(sources), encoding="utf-8")
    return {"runs": runs, "curation": curation}


def source(
    label: str,
    file_name: str,
    *,
    agentic_file: str | None = None,
    family: str = "Fixture",
    kind: str = "community",
    lane: str = "capped-thinking",
    model_id: str | None = None,
    quant_label: str | None = "Q4_K_M",
    recommended: bool = False,
) -> JsonObject:
    item: JsonObject = {
        "kind": kind,
        "family": family,
        "model_id": model_id,
        "model_label": label,
        "quant_label": quant_label,
        "file": file_name,
        "reasoning_lane": lane,
        "independent_replication": False,
        "release_date": None,
        "vram_footprint_gb": 1.0,
    }
    if recommended:
        item["recommended"] = True
    if agentic_file is not None:
        item["agentic_file"] = agentic_file
    return item


def run_record(
    *,
    lane: str = "capped-thinking",
    conformance_status: str = "headline-comparable",
    mmlu_correct: tuple[bool, ...] = (True, False),
    if_correct: tuple[bool, ...] = (True, True),
) -> JsonObject:
    benches = {
        "mmlu_pro": aggregate("mmlu_pro", mmlu_correct),
        "ifbench": aggregate("ifbench", if_correct),
    }
    return {
        "schema": "localbench-run-v0",
        "manifest": {
            "suite": {
                "suite_version": "suite-v1",
                "tier": "standard",
                "item_set_hashes": {"mmlu_pro.jsonl": "mmlu-items", "ifbench.jsonl": "ifbench-items"},
                "lane": lane,
                "caps": {"max_tokens_mcq": 16, "max_tokens_math": 0, "thinking_budget": 8},
            },
            "scorecard": {},
            "endpoint": {"runtime_reported_model": "fixture"},
            "model": {"file_sha256": "UNHASHED"},
            "runtime": {"name": None, "version": None},
            "sampling": {"temperature": 0, "top_p": None, "top_k": None, "min_p": None, "seed": None, "by_bench": {}},
        },
        "benches": benches,
        "composite": composite(benches),
        "conformance": {
            "status": conformance_status,
            "per_bench": {
                "mmlu_pro": {"truncation_rate": 0.0, "leaked_reasoning_rate": 0.0, "no_final_answer_rate": 0.0},
                "ifbench": {"truncation_rate": 0.0, "leaked_reasoning_rate": 0.0, "no_final_answer_rate": 0.0},
            },
        },
        "items": [*items("mmlu_pro", mmlu_correct), *items("ifbench", if_correct)],
        "totals": {
            "n_items": len(mmlu_correct) + len(if_correct),
            "n_errors": 0,
            "prompt_tokens": 0,
            "completion_tokens": 100,
            "total_tokens": 100,
            "wall_time_seconds": 10.0,
            "completion_tokens_per_second": 10.0,
        },
        "estimated_cost_usd": None,
        "warnings": [],
        "output_path": r"C:\local-bench\cli\runs\fixture.json",
    }


def aggregate(bench: str, correct: tuple[bool, ...]) -> JsonObject:
    raw = sum(1 for value in correct if value) / len(correct)
    return {
        "n": len(correct),
        "n_errors": 0,
        "n_extraction_failures": 0,
        "raw_accuracy": raw,
        "chance_corrected": signed_score(raw, chance=chance_for_bench(bench)),
        "termination_rate": 1.0,
        "conditional_accuracy": raw,
    }


def items(bench: str, correct: tuple[bool, ...]) -> list[JsonObject]:
    return [
        {
            "id": f"{bench}-{index}",
            "bench": bench,
            "correct": value,
            "error": None,
            "extracted": "answer" if value else None,
            "usage": {"prompt_tokens": 0, "completion_tokens": 10 * index, "total_tokens": 10 * index},
        }
        for index, value in enumerate(correct, start=1)
    ]


def composite(benches: JsonObject) -> float:
    weights = web_composite_weights()
    knowledge = object_value(benches["mmlu_pro"])["chance_corrected"]
    instruction = object_value(benches["ifbench"])["chance_corrected"]
    return (
        float_value(knowledge) * weights["knowledge"] + float_value(instruction) * weights["instruction"]
    ) / (weights["knowledge"] + weights["instruction"])


def write_run(path: Path, run: JsonObject) -> None:
    path.write_text(json.dumps(run), encoding="utf-8")


def appworld_report(successes: tuple[bool, ...]) -> JsonObject:
    results: list[JsonObject] = [
        {
            "task_id": f"scenario{index}_{index}",
            "success": success,
            "outcome": "success" if success else "failure",
        }
        for index, success in enumerate(successes, start=1)
    ]
    return {
        "report": {
            "results": results,
            "agentic_success_rate": sum(1 for success in successes if success) / len(successes),
        },
    }


def write_agentic(path: Path, record: JsonObject) -> None:
    path.write_text(json.dumps(record), encoding="utf-8")


def assert_score(value: JsonObject) -> None:
    assert {"point", "lo", "hi", "point_raw", "lo_raw", "hi_raw"} <= set(value)
    assert float_value(value["lo_raw"]) <= float_value(value["point_raw"]) <= float_value(value["hi_raw"])


def assert_axis(value: JsonObject) -> None:
    assert_score(value)
    assert {"raw_accuracy", "n", "n_errors", "n_no_answer"} <= set(value)
    assert isinstance(value["n"], int)


def read_json(path: Path) -> JsonValue:
    return json.loads(path.read_text(encoding="utf-8"))


def objects_value(value: JsonValue) -> list[JsonObject]:
    assert isinstance(value, list)
    return [object_value(item) for item in value]


def object_value(value: JsonValue) -> JsonObject:
    assert isinstance(value, dict)
    return value


def string_value(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def bool_value(value: JsonValue) -> bool:
    assert isinstance(value, bool)
    return value


def float_value(value: JsonValue) -> float:
    assert isinstance(value, int | float)
    return float(value)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

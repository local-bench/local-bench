"""End-to-end wiring tests for the suite-v1 RULER long-context axis."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Final, TypeAlias

import httpx
import pytest

from localbench._scoring import BenchAggregate, score_bench
from localbench._suite import RenderedBench, read_json_object, render_benches
from localbench._types import ItemResult, JsonValue, Usage
from localbench.orchestrate import OrchestrateConfig, run_localbench
from localbench.scorers.ruler import render_ruler_item, score_ruler

JsonObject: TypeAlias = dict[str, JsonValue]

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
_SUITE_DIR: Final = _REPO_ROOT / "suite" / "v1"
_ITEM_FILE: Final = _SUITE_DIR / "ruler_32k.jsonl"
_EXPECTED_COUNT: Final = 60
_EXPECTED_DEPTHS: Final = {0: 12, 25: 12, 50: 12, 75: 12, 100: 12}
_EXPECTED_TASKS: Final = {"niah_single": 30, "niah_multikey": 30}


def _usage(prompt_tokens: int = 0) -> Usage:
    return {"prompt_tokens": prompt_tokens, "completion_tokens": 1, "total_tokens": prompt_tokens + 1}


def _result(item_id: str, response_text: str, prompt_tokens: int = 32_100) -> ItemResult:
    return {
        "id": item_id,
        "response_text": response_text,
        "reasoning_text": None,
        "finish_reason": "stop",
        "usage": _usage(prompt_tokens),
        "latency_seconds": 0.0,
        "started_at": "2026-06-16T00:00:00+00:00",
        "finished_at": "2026-06-16T00:00:00+00:00",
        "attempts": 1,
        "error": None,
    }


def _render(max_items: int) -> RenderedBench:
    suite = read_json_object(_SUITE_DIR / "suite.json")
    warnings: list[str] = []
    benches = render_benches("ruler_32k", "standard", max_items, _SUITE_DIR, suite, warnings)
    assert warnings == [], warnings
    assert len(benches) == 1
    return benches[0]


def test_v1_long_context_axis_is_declared_in_suite() -> None:
    # Given the suite-v1 manifest.
    suite = read_json_object(_SUITE_DIR / "suite.json")

    # Then the long-context axis groups RULER 32k with equal per-axis weight.
    axes = suite["axes"]
    benches = suite["benches"]
    ruler = benches["ruler_32k"]
    assert axes["long_context"]["benches"] == ["ruler_32k"]
    assert "weight" not in axes["long_context"]
    assert ruler["template"] == "templates/ruler.txt"
    assert ruler["decoding"]["max_tokens"] == 4096
    assert ruler["itemsets"]["standard"]["item_count"] == _EXPECTED_COUNT


def test_v1_ruler_items_are_compact_seed_params_when_loaded() -> None:
    # Given the frozen compact RULER item file.
    items = _load_jsonl(_ITEM_FILE)

    # When validating row shape and stratification.
    depths: Counter[int] = Counter()
    tasks: Counter[str] = Counter()
    offenders: list[str] = []
    for index, item in enumerate(items, start=1):
        item_id = _required_str(item, "id", f"row-{index}", offenders)
        if "haystack" in item or "prompt" in item:
            offenders.append(f"{item_id}: itemset must not store rendered haystack or prompt")
        depth = _required_int(item, "target_depth_percent", item_id, offenders)
        depths[depth] += 1
        task_type = _required_str(item, "task_type", item_id, offenders)
        tasks[task_type] += 1
        _required_int(item, "seed", item_id, offenders)
        assert item["haystack_token_count"] == 32_000
        assert item["filler_corpus_id"] == "synthetic-ruler-local-v1"
        assert item["license"] == "Apache-2.0"
        assert item["generator_attribution"] == "Reimplemented from NVIDIA/RULER NIAH task pattern"

    # Then the itemset is small, balanced, and stores only regeneration parameters.
    assert len(items) == _EXPECTED_COUNT
    assert dict(depths) == _EXPECTED_DEPTHS
    assert dict(tasks) == _EXPECTED_TASKS
    assert offenders == []


def test_v1_ruler_generation_is_deterministic_and_places_needle_at_depth() -> None:
    # Given one compact RULER item.
    item = _load_jsonl(_ITEM_FILE)[18]

    # When rendering it twice from its seed and params.
    first = render_ruler_item(item)
    second = render_ruler_item(item)

    # Then the haystack is deterministic and the first answer lands near the requested depth.
    assert first == second
    assert first.haystack_token_estimate == 32_000
    needle_index = first.haystack.index(first.answers[0])
    depth_ratio = needle_index / max(1, len(first.haystack))
    expected_ratio = int(item["target_depth_percent"]) / 100
    assert depth_ratio == pytest.approx(expected_ratio, abs=0.04)


def test_v1_ruler_prompt_renders_long_context_task() -> None:
    # Given the RULER bench rendered from the suite-v1 manifest.
    bench = _render(max_items=1)

    # Then the prompt contains a regenerated long haystack and exact-answer instruction.
    prompt = bench.benchmark_items[0]["messages"][0]["content"]
    assert len(prompt.split()) > 32_000
    assert "Only return the requested value" in prompt
    assert str(bench.source_items[0]["needle_value"]) in prompt


def test_v1_ruler_dispatch_routes_to_score_ruler() -> None:
    # Given a real RULER item answered with its expected value and a wrong value.
    bench = _render(max_items=1)
    item = bench.source_items[0]
    expected = render_ruler_item(item).canonical_answer
    correct = _result(bench.benchmark_items[0]["id"], expected)
    wrong = _result(bench.benchmark_items[0]["id"], "__definitely_wrong__")

    # When scored through the production dispatch.
    scored = score_bench(bench, [correct])
    missed = score_bench(bench, [wrong])

    # Then the ruler_32k arm routes to score_ruler.
    assert scored[0]["bench"] == "ruler_32k"
    assert scored[0]["correct"] is True
    assert scored[0]["extracted"] == expected
    assert missed[0]["correct"] is False


def test_score_ruler_accepts_exact_single_and_multikey_values() -> None:
    # Given single-needle and multikey items.
    single = _load_jsonl(_ITEM_FILE)[0]
    multikey = next(item for item in _load_jsonl(_ITEM_FILE) if item["task_type"] == "niah_multikey")

    # When scoring canonical answers.
    single_score = score_ruler(single, str(single["needle_value"]))
    multi_score = score_ruler(multikey, json.dumps(render_ruler_item(multikey).answers))

    # Then exact expected values are accepted and extra prose is not.
    assert single_score == {"correct": True, "extracted": str(single["needle_value"])}
    assert multi_score["correct"] is True
    assert score_ruler(single, f"The value is {single['needle_value']}")["correct"] is False


def test_ruler_truncation_assertion_flags_materially_short_usage(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given a RULER run where the endpoint reports only a 16k prompt for a 32k prompt.
        output_path = tmp_path / "run.json"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
            payload = json.loads(request.content)
            assert len(payload["messages"][0]["content"].split()) > 32_000
            return _completion("not-the-answer", prompt_tokens=16_000)

        # When running one RULER item through the orchestrator.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=_SUITE_DIR,
                bench="ruler_32k",
                tier="standard",
                out=output_path,
                max_items=1,
            ),
            transport=httpx.MockTransport(handler),
        )

        # Then the run and item both carry a clear truncation flag.
        assert any("serving-truncation suspected" in warning for warning in record["warnings"])
        assert any(
            "serving-truncation suspected" in warning
            for warning in record["items"][0]["warnings"]
        )
        assert record["items"][0]["correct"] is False

    asyncio.run(scenario())


def test_existing_five_axis_composite_is_unchanged_when_long_context_domain_is_absent() -> None:
    # Given the suite-v1 domains present before adding Long-Context.
    from localbench._scoring import composite

    benches: dict[str, BenchAggregate] = {
        "mmlu_pro": _aggregate(0.50),
        "ifbench": _aggregate(0.60),
        "bfcl": _aggregate(0.70),
        "amo": _aggregate(0.80),
        "lcb": _aggregate(0.90),
    }

    # When computing the composite with Long-Context declared but absent from the run.
    result = composite(benches)

    # Then only the HEADLINE axes (knowledge=mmlu_pro + instruction=ifbench) enter
    # the composite; agentic/math/coding are present but weight 0.0
    # (METHODOLOGY-v1.2 §3), so adding/removing them never moves the headline.
    assert result == pytest.approx((0.50 + 0.60) / 2)


def test_v1_ruler_itemset_hash_matches_suite_and_lock() -> None:
    # Given the suite manifest and lockfile.
    suite = read_json_object(_SUITE_DIR / "suite.json")
    lock = read_json_object(_SUITE_DIR / "itemsets.lock.json")

    # When reading the ruler itemset references.
    suite_entry = _object(_object(_object(suite["benches"])["ruler_32k"])["itemsets"])["standard"]
    lock_entry = _object(_object(lock["files"])["ruler_32k.jsonl"])

    # Then suite.json and itemsets.lock.json agree on count, hash, and provenance.
    assert _object(suite_entry)["item_count"] == _EXPECTED_COUNT
    assert _object(suite_entry)["sha256"] == lock_entry["sha256"]
    assert lock_entry["item_count"] == _EXPECTED_COUNT
    assert lock_entry["source_dataset"] == "NVIDIA/RULER"
    assert lock_entry["license"] == "Apache-2.0"
    assert lock_entry["target_context"] == "32k"


def _load_jsonl(path: Path) -> list[JsonObject]:
    rows: list[JsonObject] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise AssertionError(f"{path.name}:{line_number} is not a JSON object")
            rows.append(parsed)
    return rows


def _completion(text: str, prompt_tokens: int) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"content": text},
                    "finish_reason": "stop",
                },
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 1,
                "total_tokens": prompt_tokens + 1,
            },
        },
    )


def _aggregate(score: float) -> BenchAggregate:
    return {
        "n": 10,
        "n_errors": 0,
        "n_extraction_failures": 0,
        "raw_accuracy": score,
        "chance_corrected": score,
    }


def _required_str(
    row: JsonObject,
    key: str,
    item_id: str,
    offenders: list[str],
) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        offenders.append(f"{item_id}: {key} must be a non-empty string")
        return ""
    return value


def _required_int(
    row: JsonObject,
    key: str,
    item_id: str,
    offenders: list[str],
) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        offenders.append(f"{item_id}: {key} must be an integer")
        return 0
    return value


def _object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise AssertionError(f"expected object, got {type(value).__name__}")
    return value

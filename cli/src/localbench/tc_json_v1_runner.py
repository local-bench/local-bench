from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import NotRequired, TypedDict

import httpx

from localbench._suite import read_json_object, render_benches
from localbench._types import JsonObject, JsonValue
from localbench.runner import run_benchmark
from localbench.scorers.tc_json_v1 import score_tc_json_v1


class RateInterval(TypedDict):
    point: float
    lo: float
    hi: float


class TCJsonRunnerItem(TypedDict):
    id: str
    response_text: str | None
    extracted: str | None
    correct: bool
    failure_reason: str | None
    diagnostics: JsonObject


class TCJsonAggregate(TypedDict):
    n: int
    correct: int
    raw_asr: float
    wilson_95_ci: RateInterval
    invalid_json_rate: float
    failure_rates: dict[str, float]
    band: str


class TCJsonRunRecord(TypedDict):
    bench: str
    model: str
    base_url: str
    items: list[TCJsonRunnerItem]
    aggregate: TCJsonAggregate
    output_path: NotRequired[str]


async def run_tc_json_v1(
    *,
    base_url: str,
    model: str,
    suite_dir: Path,
    out: Path | None = None,
    api_key: str | None = None,
    max_items: int | None = None,
    concurrency: int = 4,
    transport: httpx.AsyncBaseTransport | None = None,
) -> TCJsonRunRecord:
    suite = read_json_object(suite_dir / "suite.json")
    warnings: list[str] = []
    benches = render_benches("tc_json_v1", "standard", max_items, suite_dir, suite, warnings)
    if len(benches) != 1:
        raise TCJsonRunnerError("tc_json_v1 bench is not renderable from the suite")
    bench = benches[0]
    run = await run_benchmark(
        base_url=base_url,
        model=model,
        items=bench.benchmark_items,
        api_key=api_key,
        concurrency=concurrency,
        transport=transport,
        max_attempts=1,
    )
    items: list[TCJsonRunnerItem] = []
    for source_item, result in zip(bench.source_items, run["results"], strict=True):
        response_text = result["response_text"] or ""
        score = score_tc_json_v1(source_item, response_text)
        diagnostics: JsonObject = {
            "extra_call": score["diagnostics"]["extra_call"],
            "missing_call": score["diagnostics"]["missing_call"],
            "arg_mismatch": score["diagnostics"]["arg_mismatch"],
        }
        items.append(
            {
                "id": str(source_item["id"]),
                "response_text": result["response_text"],
                "extracted": score["extracted"],
                "correct": score["correct"],
                "failure_reason": score["failure_reason"],
                "diagnostics": diagnostics,
            }
        )
    record: TCJsonRunRecord = {
        "bench": "tc_json_v1",
        "model": model,
        "base_url": base_url.rstrip("/"),
        "items": items,
        "aggregate": _aggregate(items),
    }
    if out is not None:
        record["output_path"] = str(out)
        _write_json(record, out)
    return record


class TCJsonRunnerError(RuntimeError):
    pass


def _aggregate(items: list[TCJsonRunnerItem]) -> TCJsonAggregate:
    total = len(items)
    correct = sum(1 for item in items if item["correct"])
    raw_asr = correct / total if total else 0.0
    failures = Counter(item["failure_reason"] for item in items if item["failure_reason"] is not None)
    failure_rates = {key: value / total for key, value in sorted(failures.items())} if total else {}
    invalid_json_rate = failures.get("invalid_json", 0) / total if total else 0.0
    return {
        "n": total,
        "correct": correct,
        "raw_asr": raw_asr,
        "wilson_95_ci": wilson_95_ci(successes=correct, total=total),
        "invalid_json_rate": invalid_json_rate,
        "failure_rates": failure_rates,
        "band": gate_band(raw_asr=raw_asr, invalid_json_rate=invalid_json_rate),
    }


def wilson_95_ci(*, successes: int, total: int) -> RateInterval:
    if total <= 0:
        return {"point": 0.0, "lo": 0.0, "hi": 1.0}
    z = 1.959963984540054
    point = successes / total
    denom = 1 + z * z / total
    center = (point + z * z / (2 * total)) / denom
    margin = z * ((point * (1 - point) + z * z / (4 * total)) / total) ** 0.5 / denom
    return {"point": point, "lo": max(0.0, center - margin), "hi": min(1.0, center + margin)}


def gate_band(*, raw_asr: float, invalid_json_rate: float) -> str:
    if raw_asr < 0.60 or invalid_json_rate > 0.15:
        return "RED"
    if raw_asr >= 0.80 and invalid_json_rate <= 0.05:
        return "GREEN"
    return "AMBER"


def _write_json(record: TCJsonRunRecord, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)
        handle.write("\n")

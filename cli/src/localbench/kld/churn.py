"""Task churn between a reference run and a quantized run.

Churn = the fraction of items whose correctness FLIPS between the full-precision
(or Q8-proxy) reference and a quant, on identical items. Per METHODOLOGY-v1.2 §6 it
is the free, universal middle metric: it needs no FP16 logits (just two task runs)
and surfaces hidden behavioral change that net accuracy hides (~12% of answers flip
at Q4 on Gemma-12B despite flat accuracy). Pair it with KLD + the task delta.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass

from localbench._types import JsonValue


@dataclass(frozen=True, slots=True)
class ChurnResult:
    n: int
    flips: int
    churn: float
    by_bench: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def compute_churn(
    reference: Mapping[str, JsonValue],
    quant: Mapping[str, JsonValue],
) -> ChurnResult:
    """Fraction of items whose `correct` flips between two paired run records."""
    ref = _correct_map(reference)
    qnt = _correct_map(quant)
    if set(ref) != set(qnt):
        raise ValueError("churn requires the same item ids in both runs")
    flips = 0
    per_bench_n: dict[str, int] = {}
    per_bench_flips: dict[str, int] = {}
    for key, ref_correct in ref.items():
        bench = key[0]
        per_bench_n[bench] = per_bench_n.get(bench, 0) + 1
        if ref_correct != qnt[key]:
            flips += 1
            per_bench_flips[bench] = per_bench_flips.get(bench, 0) + 1
    n = len(ref)
    by_bench = {
        bench: per_bench_flips.get(bench, 0) / count
        for bench, count in sorted(per_bench_n.items())
    }
    return ChurnResult(n=n, flips=flips, churn=flips / n if n else 0.0, by_bench=by_bench)


def _correct_map(record: Mapping[str, JsonValue]) -> dict[tuple[str, str], bool]:
    raw_items = record.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("run record must contain an items list")
    out: dict[tuple[str, str], bool] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise ValueError("run item must be a JSON object")
        item_id = raw_item.get("id")
        bench = raw_item.get("bench")
        correct = raw_item.get("correct")
        if not isinstance(item_id, str) or not isinstance(bench, str) or not isinstance(correct, bool):
            raise ValueError("run items must include string id, string bench, and bool correct")
        key = (bench, item_id)
        if key in out:
            raise ValueError(f"duplicate item id in run record: {bench}/{item_id}")
        out[key] = correct
    return out

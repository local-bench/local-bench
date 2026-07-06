from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from localbench._types import JsonObject

_COVERAGE_THRESHOLD = 0.8


@dataclass(frozen=True, slots=True)
class _TimingMetric:
    bench: str
    prompt_n: float
    prompt_ms: float
    predicted_n: float
    predicted_ms: float


def perf_summary(items: Sequence[Mapping[str, object]]) -> JsonObject:
    metrics = [_metric for item in items if (_metric := _item_metric(item)) is not None]
    coverage = len(metrics) / len(items) if items else 0.0
    source = "llama.cpp" if metrics else None
    if coverage < _COVERAGE_THRESHOLD:
        return _empty_perf(source, coverage)
    prompt_ms_values = [metric.prompt_ms for metric in metrics]
    predicted_ms_values = [metric.predicted_ms for metric in metrics]
    prompt_ms_median = _percentile(prompt_ms_values, 0.5)
    return {
        "timings_source": source,
        "timings_coverage": coverage,
        "prefill_tps": _tokens_per_second(metrics, token_field="prompt_n", ms_field="prompt_ms"),
        "decode_tps": _tokens_per_second(
            metrics,
            token_field="predicted_n",
            ms_field="predicted_ms",
        ),
        "prompt_ms_median": prompt_ms_median,
        "prompt_ms_p95": _percentile(prompt_ms_values, 0.95),
        "predicted_ms_median": _percentile(predicted_ms_values, 0.5),
        "predicted_ms_p95": _percentile(predicted_ms_values, 0.95),
        # Non-streaming runner: true TTFT is unmeasured; prompt_ms is the deterministic lower-bound proxy.
        "ttft_proxy_ms_median": prompt_ms_median,
        "per_bench": _per_bench(metrics),
    }


def _empty_perf(source: str | None, coverage: float) -> JsonObject:
    return {
        "timings_source": source,
        "timings_coverage": coverage,
        "prefill_tps": None,
        "decode_tps": None,
        "prompt_ms_median": None,
        "prompt_ms_p95": None,
        "predicted_ms_median": None,
        "predicted_ms_p95": None,
        "ttft_proxy_ms_median": None,
        "per_bench": {},
    }


def _item_metric(item: Mapping[str, object]) -> _TimingMetric | None:
    timings = item.get("server_timings")
    if not isinstance(timings, dict):
        return None
    passes = timings.get("passes")
    if not isinstance(passes, list) or not passes:
        return None
    prompt_n = 0.0
    prompt_ms = 0.0
    predicted_n = 0.0
    predicted_ms = 0.0
    for timing_pass in passes:
        if not isinstance(timing_pass, dict):
            return None
        pass_prompt_n = _number(timing_pass.get("prompt_n"))
        pass_prompt_ms = _number(timing_pass.get("prompt_ms"))
        pass_predicted_n = _number(timing_pass.get("predicted_n"))
        pass_predicted_ms = _number(timing_pass.get("predicted_ms"))
        if (
            pass_prompt_n is None
            or pass_prompt_ms is None
            or pass_predicted_n is None
            or pass_predicted_ms is None
        ):
            return None
        prompt_n += pass_prompt_n
        prompt_ms += pass_prompt_ms
        predicted_n += pass_predicted_n
        predicted_ms += pass_predicted_ms
    bench = item.get("bench")
    return _TimingMetric(
        bench=bench if isinstance(bench, str) else "unknown",
        prompt_n=prompt_n,
        prompt_ms=prompt_ms,
        predicted_n=predicted_n,
        predicted_ms=predicted_ms,
    )


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _tokens_per_second(
    metrics: Sequence[_TimingMetric],
    *,
    token_field: str,
    ms_field: str,
) -> float | None:
    tokens = sum(float(getattr(metric, token_field)) for metric in metrics)
    milliseconds = sum(float(getattr(metric, ms_field)) for metric in metrics)
    if milliseconds <= 0:
        return None
    return tokens * 1000.0 / milliseconds


def _per_bench(metrics: Sequence[_TimingMetric]) -> JsonObject:
    by_bench: dict[str, list[_TimingMetric]] = defaultdict(list)
    for metric in metrics:
        by_bench[metric.bench].append(metric)
    return {
        bench: {
            "prefill_tps": _tokens_per_second(
                bench_metrics,
                token_field="prompt_n",
                ms_field="prompt_ms",
            ),
            "decode_tps": _tokens_per_second(
                bench_metrics,
                token_field="predicted_n",
                ms_field="predicted_ms",
            ),
            "prompt_ms_median": _percentile(
                [metric.prompt_ms for metric in bench_metrics],
                0.5,
            ),
            "n": len(bench_metrics),
        }
        for bench, bench_metrics in by_bench.items()
    }


def _percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    fraction = pos - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction

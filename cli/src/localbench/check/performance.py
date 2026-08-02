from __future__ import annotations

import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.check.types import CheckError

PREFILL_BUCKETS: Final = (512, 4096, 16384)
DECODE_TOKENS: Final = 256
DECODE_REPETITIONS: Final = 5


@dataclass(frozen=True, slots=True)
class PerfCase:
    kind: str
    prompt_tokens: int
    output_tokens: int
    cold: bool = False
    repetition: int | None = None


Probe = Callable[[PerfCase], JsonObject]
VramReader = Callable[[str], float]


def run_perf_phase(
    *,
    probe: Probe,
    read_vram_mb: VramReader,
    environment: JsonObject,
) -> JsonObject:
    _validate_environment(environment)
    idle_vram = read_vram_mb("idle")
    cold = probe(PerfCase("ttft", 512, 1, cold=True))
    loaded_vram = read_vram_mb("loaded")
    warm = probe(PerfCase("ttft", 512, 1, cold=False))

    prefill: JsonObject = {}
    for tokens in PREFILL_BUCKETS:
        sample = probe(PerfCase("prefill", tokens, 1))
        elapsed_ms = _required_number(sample, "prefill_ms")
        prefill[str(tokens)] = {
            "tokens": tokens,
            "tokens_per_second": _rate(tokens, elapsed_ms),
        }

    decode_values = [
        _rate(
            DECODE_TOKENS,
            _required_number(
                probe(PerfCase("decode", 512, DECODE_TOKENS, repetition=repetition)),
                "decode_ms",
            ),
        )
        for repetition in range(DECODE_REPETITIONS)
    ]
    peak_vram = read_vram_mb("peak")
    decode_value_rows: list[JsonValue] = [value for value in decode_values]
    return {
        "decode": {
            "iqr_tokens_per_second": _percentile(decode_values, 0.75) - _percentile(decode_values, 0.25),
            "median_tokens_per_second": statistics.median(decode_values),
            "repetitions": DECODE_REPETITIONS,
            "tokens": DECODE_TOKENS,
            "values_tokens_per_second": decode_value_rows,
        },
        "environment": environment,
        "prefill": prefill,
        "schema_version": "localbench-check-perf-v1",
        "ttft": {
            "cold_ms": _required_number(cold, "ttft_ms"),
            "warm_ms": _required_number(warm, "ttft_ms"),
        },
        "vram": {
            "idle_mb": idle_vram,
            "loaded_mb": loaded_vram,
            "peak_mb": max(idle_vram, loaded_vram, peak_vram),
            "source": "NVML",
        },
    }


def naturalistic_task_telemetry(items: Sequence[JsonObject]) -> JsonObject:
    rows: list[JsonValue] = []
    for item in items:
        generation = item.get("candidate")
        params = item.get("generation_parameters")
        if not isinstance(generation, dict) or not isinstance(params, dict):
            raise CheckError("task telemetry requires candidate generation and parameter records")
        usage = generation.get("usage")
        token_ids = generation.get("token_ids")
        think_budget = params.get("think_budget")
        rows.append(
            {
                "completion_tokens": len(token_ids) if isinstance(token_ids, list) else _optional_int(usage, "completion_tokens"),
                "item_id": _required_str(item, "item_id"),
                "latency_seconds": _optional_number(generation.get("latency_seconds")),
                "module": _required_str(item, "module"),
                "prompt_tokens": _optional_int(usage, "prompt_tokens"),
                "reasoning_tokens": _optional_int(usage, "reasoning_tokens"),
                "think_budget_tokens": think_budget if isinstance(think_budget, int) else None,
                "thinking": "on" if isinstance(think_budget, int) and think_budget > 0 else "off",
            }
        )
    return {"items": rows, "label": "naturalistic"}


def mock_performance(items: Sequence[JsonObject], execution: JsonObject) -> JsonObject:
    prefill_rates = {512: 950.0, 4096: 1120.0, 16384: 1060.0}
    decode_rates = (48.0, 50.0, 51.0, 49.0, 52.0)

    def probe(case: PerfCase) -> JsonObject:
        if case.kind == "ttft":
            return {"decode_ms": 20.0, "prefill_ms": 10.0, "ttft_ms": 125.0 if case.cold else 24.0}
        if case.kind == "prefill":
            return {
                "decode_ms": 20.0,
                "prefill_ms": case.prompt_tokens * 1000.0 / prefill_rates[case.prompt_tokens],
                "ttft_ms": 24.0,
            }
        repetition = case.repetition
        if repetition is None:
            raise CheckError("mock decode sample has no repetition index")
        return {
            "decode_ms": DECODE_TOKENS * 1000.0 / decode_rates[repetition],
            "prefill_ms": 10.0,
            "ttft_ms": 24.0,
        }

    environment: JsonObject = {
        "binary_sha256s": execution.get("binaries", {}),
        "context_tokens": execution.get("context_tokens"),
        "cuda": execution.get("cuda_version"),
        "driver": execution.get("driver"),
        "flags": execution.get("flags", []),
        "framework": f"llama.cpp {execution.get('build', 'unknown')}",
        "gpu": "mock",
    }
    controlled = run_perf_phase(
        probe=probe,
        read_vram_mb=lambda label: {"idle": 1024.0, "loaded": 4096.0, "peak": 4608.0}[label],
        environment=environment,
    )
    controlled["runner"] = "mock"
    return {
        "controlled": controlled,
        "schema_version": "localbench-check-performance-record-v1",
        "task_phase": naturalistic_task_telemetry(items),
    }


def _validate_environment(environment: JsonObject) -> None:
    required = {"gpu", "driver", "cuda", "binary_sha256s", "flags", "context_tokens", "framework"}
    missing = sorted(required - environment.keys())
    if missing:
        raise CheckError(f"performance environment identity is incomplete: {', '.join(missing)}")


def _rate(tokens: int, milliseconds: float) -> float:
    if milliseconds <= 0.0:
        raise CheckError("performance durations must be positive")
    return tokens * 1000.0 / milliseconds


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _required_number(row: JsonObject, key: str) -> float:
    value = row.get(key)
    number = _optional_number(value)
    if number is None:
        raise CheckError(f"performance probe field {key!r} must be numeric")
    return number


def _optional_number(value: JsonValue) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return float(value)


def _optional_int(row: JsonValue, key: str) -> int | None:
    if not isinstance(row, dict):
        return None
    value = row.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _required_str(row: JsonObject, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise CheckError(f"task telemetry field {key!r} must be a non-empty string")
    return value

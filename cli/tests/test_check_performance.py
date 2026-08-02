from __future__ import annotations

from localbench._types import JsonObject
from localbench.check.performance import PerfCase, naturalistic_task_telemetry, run_perf_phase


def test_perf_phase_runs_locked_cases_and_summarizes_decode_and_nvml() -> None:
    calls: list[PerfCase] = []

    def probe(case: PerfCase) -> JsonObject:
        calls.append(case)
        return {
            "decode_ms": case.output_tokens * 20.0,
            "prefill_ms": case.prompt_tokens * 2.0,
            "ttft_ms": 120.0 if case.cold else 25.0,
        }

    readings = {"idle": 1000.0, "loaded": 2500.0, "peak": 3100.0}
    environment: JsonObject = {
        "gpu": "Mock GPU",
        "driver": "999.0",
        "cuda": "13.3",
        "binary_sha256s": {"llama-server.exe": "a" * 64},
        "flags": ["-ctk", "f16"],
        "context_tokens": 32768,
        "framework": "llama.cpp b10076",
    }

    result = run_perf_phase(
        probe=probe,
        read_vram_mb=lambda label: readings[label],
        environment=environment,
    )

    assert result["ttft"] == {"cold_ms": 120.0, "warm_ms": 25.0}
    assert result["prefill"] == {
        "512": {"tokens": 512, "tokens_per_second": 500.0},
        "4096": {"tokens": 4096, "tokens_per_second": 500.0},
        "16384": {"tokens": 16384, "tokens_per_second": 500.0},
    }
    decode = result["decode"]
    assert isinstance(decode, dict)
    assert decode["tokens"] == 256
    assert decode["repetitions"] == 5
    assert decode["median_tokens_per_second"] == 50.0
    assert decode["iqr_tokens_per_second"] == 0.0
    assert result["vram"] == {"idle_mb": 1000.0, "loaded_mb": 2500.0, "peak_mb": 3100.0, "source": "NVML"}
    assert len(calls) == 10
    assert [case.prompt_tokens for case in calls if case.kind == "prefill"] == [512, 4096, 16384]
    assert sum(case.kind == "decode" for case in calls) == 5


def test_naturalistic_task_telemetry_records_every_item_without_relabeling_controlled() -> None:
    items: list[JsonObject] = [
        {
            "item_id": "k-1",
            "module": "knowledge",
            "candidate": {
                "token_ids": [1, 2, 3],
                "usage": {"prompt_tokens": 100, "reasoning_tokens": 2},
                "latency_seconds": 1.25,
            },
            "generation_parameters": {"think_budget": 4096},
        },
        {
            "item_id": "m-1",
            "module": "math",
            "candidate": {"token_ids": [4, 5], "latency_seconds": 0.5},
            "generation_parameters": {"think_budget": 4096},
        },
    ]

    telemetry = naturalistic_task_telemetry(items)

    assert telemetry["label"] == "naturalistic"
    rows = telemetry["items"]
    assert isinstance(rows, list)
    assert rows == [
        {
            "completion_tokens": 3,
            "item_id": "k-1",
            "latency_seconds": 1.25,
            "module": "knowledge",
            "prompt_tokens": 100,
            "reasoning_tokens": 2,
            "think_budget_tokens": 4096,
            "thinking": "on",
        },
        {
            "completion_tokens": 2,
            "item_id": "m-1",
            "latency_seconds": 0.5,
            "module": "math",
            "prompt_tokens": None,
            "reasoning_tokens": None,
            "think_budget_tokens": 4096,
            "thinking": "on",
        },
    ]

from __future__ import annotations

import pytest

from localbench.perf import perf_summary


def _timed_item(bench: str, item_id: str, passes: list[dict[str, object]]) -> dict[str, object]:
    return {
        "bench": bench,
        "id": item_id,
        "score": 1.0,
        "server_timings": {"passes": passes},
    }


def _untimed_item(bench: str, item_id: str) -> dict[str, object]:
    return {"bench": bench, "id": item_id, "score": 1.0}


def test_perf_summary_weighted_rates_medians_and_two_pass_summation() -> None:
    perf = perf_summary(
        [
            _timed_item(
                "math",
                "two-pass",
                [
                    {"prompt_n": 10, "prompt_ms": 50.0, "predicted_n": 5, "predicted_ms": 20.0},
                    {
                        "prompt_n": 20,
                        "prompt_ms": 100.0,
                        "predicted_n": 5,
                        "predicted_ms": 30.0,
                    },
                ],
            ),
            _timed_item(
                "math",
                "single",
                [{"prompt_n": 30, "prompt_ms": 50.0, "predicted_n": 10, "predicted_ms": 50.0}],
            ),
            _timed_item(
                "coding",
                "single",
                [{"prompt_n": 60, "prompt_ms": 100.0, "predicted_n": 30, "predicted_ms": 60.0}],
            ),
        ]
    )

    assert perf["timings_source"] == "llama.cpp"
    assert perf["timings_coverage"] == 1.0
    assert perf["prefill_tps"] == pytest.approx(400.0)
    assert perf["decode_tps"] == pytest.approx(312.5)
    assert perf["prompt_ms_median"] == pytest.approx(100.0)
    assert perf["prompt_ms_p95"] == pytest.approx(145.0)
    assert perf["predicted_ms_median"] == pytest.approx(50.0)
    assert perf["predicted_ms_p95"] == pytest.approx(59.0)
    assert perf["ttft_proxy_ms_median"] == pytest.approx(100.0)
    assert perf["per_bench"] == {
        "math": {
            "prefill_tps": pytest.approx(300.0),
            "decode_tps": pytest.approx(200.0),
            "prompt_ms_median": pytest.approx(100.0),
            "n": 2,
        },
        "coding": {
            "prefill_tps": pytest.approx(600.0),
            "decode_tps": pytest.approx(500.0),
            "prompt_ms_median": pytest.approx(100.0),
            "n": 1,
        },
    }


def test_perf_summary_below_coverage_threshold_reports_only_coverage() -> None:
    perf = perf_summary(
        [
            _timed_item(
                "math",
                "timed-1",
                [{"prompt_n": 10, "prompt_ms": 50.0, "predicted_n": 5, "predicted_ms": 20.0}],
            ),
            _timed_item(
                "math",
                "timed-2",
                [{"prompt_n": 10, "prompt_ms": 50.0, "predicted_n": 5, "predicted_ms": 20.0}],
            ),
            _timed_item(
                "math",
                "timed-3",
                [{"prompt_n": 10, "prompt_ms": 50.0, "predicted_n": 5, "predicted_ms": 20.0}],
            ),
            _untimed_item("math", "untimed-1"),
            _untimed_item("coding", "untimed-2"),
        ]
    )

    assert perf["timings_source"] == "llama.cpp"
    assert perf["timings_coverage"] == pytest.approx(0.6)
    assert perf["prefill_tps"] is None
    assert perf["decode_tps"] is None
    assert perf["prompt_ms_median"] is None
    assert perf["prompt_ms_p95"] is None
    assert perf["predicted_ms_median"] is None
    assert perf["predicted_ms_p95"] is None
    assert perf["ttft_proxy_ms_median"] is None
    assert perf["per_bench"] == {}

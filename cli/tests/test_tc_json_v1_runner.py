from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from localbench.tc_json_v1_runner import gate_band, run_tc_json_v1, wilson_95_ci

REPO_ROOT = Path(__file__).resolve().parents[2]
SUITE_DIR = REPO_ROOT / "suite" / "v1"


def test_run_tc_json_v1_when_mock_client_returns_canned_responses_writes_gate_record(tmp_path: Path) -> None:
    async def scenario() -> None:
        source_items = _load_items()[:3]
        responses = [
            json.dumps({"schema_version": "localbench.tc.v1", "calls": source_items[0]["gold"]["calls"]}),
            json.dumps({"schema_version": "localbench.tc.v1", "calls": []}),
            "not json",
        ]
        seen_prompts: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            seen_prompts.append(payload["messages"][0]["content"])
            index = len(seen_prompts) - 1
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": responses[index]}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
            )

        out = tmp_path / "tc_json_results.json"
        record = await run_tc_json_v1(
            base_url="http://local/v1",
            model="mock-model",
            suite_dir=SUITE_DIR,
            out=out,
            max_items=3,
            concurrency=1,
            transport=httpx.MockTransport(handler),
        )

        written = json.loads(out.read_text(encoding="utf-8"))
        assert len(seen_prompts) == 3
        assert all("localbench.tc.v1" in prompt for prompt in seen_prompts)
        assert record["aggregate"]["n"] == 3
        assert record["aggregate"]["correct"] == 1
        assert record["aggregate"]["raw_asr"] == pytest.approx(1 / 3)
        assert record["aggregate"]["band"] == "RED"
        assert record["aggregate"]["failure_rates"]["invalid_json"] == pytest.approx(1 / 3)
        assert record["items"][0]["correct"] is True
        assert record["items"][1]["failure_reason"] == "wrong_call_count"
        assert record["items"][2]["failure_reason"] == "invalid_json"
        assert written["aggregate"] == record["aggregate"]

    asyncio.run(scenario())


def test_tc_json_v1_runner_gate_band_when_rates_cross_thresholds() -> None:
    assert gate_band(raw_asr=0.82, invalid_json_rate=0.05) == "GREEN"
    assert gate_band(raw_asr=0.70, invalid_json_rate=0.01) == "AMBER"
    assert gate_band(raw_asr=0.90, invalid_json_rate=0.16) == "RED"


def test_wilson_95_ci_when_given_empty_and_nonempty_counts() -> None:
    empty = wilson_95_ci(successes=0, total=0)
    nonempty = wilson_95_ci(successes=2, total=3)

    assert empty == {"point": 0.0, "lo": 0.0, "hi": 1.0}
    assert nonempty["point"] == pytest.approx(2 / 3)
    assert nonempty["lo"] < nonempty["point"] < nonempty["hi"]


def _load_items() -> list[dict[str, object]]:
    path = SUITE_DIR / "tc_json_v1.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from localbench.orchestrate import OrchestrateConfig, run_localbench
from localbench.persistence import atomic_write_bytes, atomic_write_json

FIXTURE_SUITE = Path(__file__).parent / "fixtures" / "suite_v0"


def test_atomic_write_json_when_target_is_nested(tmp_path: Path) -> None:
    # Given: a nested destination and a JSON payload.
    target = tmp_path / "nested" / "record.json"
    payload = {"schema_version": "test", "items": [1, 2, 3]}

    # When: writing atomically.
    atomic_write_json(payload, target)

    # Then: the destination contains complete formatted JSON and no temp file remains.
    assert json.loads(target.read_text(encoding="utf-8")) == payload
    assert list(target.parent.glob(".record.json.*.tmp")) == []


def test_atomic_write_bytes_when_replace_hits_transient_permission_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Given: os.replace fails once with a transient Windows-style PermissionError.
    target = tmp_path / "data.bin"
    calls = 0

    def flaky_replace(src: str | bytes | Path, dst: str | bytes | Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("transient handle")
        original_replace(src, dst)

    original_replace = __import__("os").replace
    monkeypatch.setattr("localbench.persistence.os.replace", flaky_replace)

    # When: writing bytes atomically.
    atomic_write_bytes(b"complete", target, retry_delay_seconds=0)

    # Then: the write is retried and completed.
    assert target.read_bytes() == b"complete"
    assert calls == 2


def test_run_localbench_writes_campaign_json_and_status(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: a one-item run against a mock OpenAI-compatible endpoint.
        output_path = tmp_path / "campaign" / "localbench-run.json"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "Answer: A"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )

        # When: running the orchestrator.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                max_items=1,
                out=output_path,
            ),
            transport=httpx.MockTransport(handler),
        )

        # Then: campaign.json is immutable input metadata and status reaches completion.
        campaign = json.loads((tmp_path / "campaign" / "campaign.json").read_text(encoding="utf-8"))
        status = json.loads((tmp_path / "campaign" / "run.status.json").read_text(encoding="utf-8"))
        assert campaign["schema_version"] == "localbench-campaign-v1"
        assert campaign["model"]["declared_model_id"] == "demo-model"
        assert campaign["suite"]["suite_hash"]
        assert campaign["benches"] == ["mmlu_pro"]
        assert campaign["items"]["total"] == 1
        assert campaign["provider"]["name"] == "local"
        assert campaign["serve_fingerprint"]["serve_mode"] is None
        assert "api" not in json.dumps(campaign).lower()
        assert status["state"] == "complete"
        assert status["completed_items"] == 1
        assert json.loads(output_path.read_text(encoding="utf-8")) == record

    asyncio.run(scenario())

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from localbench.orchestrate import OrchestrateConfig, UnsafeResumeError, run_localbench
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


def test_run_localbench_writes_complete_bench_checkpoint(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: a two-item bench run.
        output_path = tmp_path / "campaign" / "localbench-run.json"

        # When: the bench completes.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                max_items=2,
                out=output_path,
            ),
            transport=httpx.MockTransport(_answer_a_handler),
        )

        # Then: bench raw, scored, aggregate, and complete files are durable on disk.
        bench_dir = tmp_path / "campaign" / "benchmarks"
        raw_lines = (bench_dir / "mmlu_pro.raw_results.jsonl").read_text(encoding="utf-8").splitlines()
        scored_lines = (bench_dir / "mmlu_pro.scored_items.jsonl").read_text(encoding="utf-8").splitlines()
        aggregate = json.loads((bench_dir / "mmlu_pro.aggregate.json").read_text(encoding="utf-8"))
        complete = json.loads((bench_dir / "mmlu_pro.complete.json").read_text(encoding="utf-8"))
        assert len(raw_lines) == 2
        assert len(scored_lines) == 2
        assert aggregate == record["benches"]["mmlu_pro"]
        assert complete["bench"] == "mmlu_pro"
        assert complete["raw_count"] == 2
        assert complete["scored_count"] == 2

    asyncio.run(scenario())


def test_run_localbench_resume_skips_completed_benches(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: an already completed campaign.
        output_path = tmp_path / "campaign" / "localbench-run.json"
        original = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                max_items=2,
                out=output_path,
            ),
            transport=httpx.MockTransport(_answer_a_handler),
        )
        output_path.unlink()
        requested_items: list[str] = []

        def fail_on_chat(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
            requested_items.append(json.loads(request.content)["messages"][0]["content"])
            return httpx.Response(500, text="completed item was requested again")

        # When: resuming from that campaign directory.
        resumed = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                max_items=2,
                out=output_path,
                resume=tmp_path / "campaign",
            ),
            transport=httpx.MockTransport(fail_on_chat),
        )

        # Then: no completed item is requested and the final artifact is reassembled.
        assert requested_items == []
        assert resumed["items"] == original["items"]
        assert resumed["benches"] == original["benches"]
        assert resumed["resumed"] is True
        assert json.loads(output_path.read_text(encoding="utf-8")) == resumed

    asyncio.run(scenario())


def test_run_localbench_resume_refuses_hard_invariant_mismatch(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: a campaign whose immutable model identity was tampered with.
        output_path = tmp_path / "campaign" / "localbench-run.json"
        await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                max_items=1,
                out=output_path,
            ),
            transport=httpx.MockTransport(_answer_a_handler),
        )
        campaign_path = tmp_path / "campaign" / "campaign.json"
        campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
        campaign["model"]["declared_model_id"] = "other-model"
        atomic_write_json(campaign, campaign_path)

        # When / Then: resume refuses before making model requests.
        with pytest.raises(UnsafeResumeError):
            await run_localbench(
                OrchestrateConfig(
                    endpoint="http://local/v1",
                    model="demo-model",
                    suite_dir=FIXTURE_SUITE,
                    bench="mmlu_pro",
                    max_items=1,
                    out=output_path,
                    resume=tmp_path / "campaign",
                ),
                transport=httpx.MockTransport(_answer_a_handler),
            )

    asyncio.run(scenario())


def _answer_a_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "Answer: A"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )

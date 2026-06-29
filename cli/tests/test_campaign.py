from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from localbench.campaign import campaign_paths
from localbench.campaign_checkpoints import (
    CheckpointCorruptionError,
    ExpectedItemCheckpoint,
    append_item_checkpoint,
    read_partial_item_checkpoints,
)
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
        raw_record = json.loads(raw_lines[0])
        scored_record = json.loads(scored_lines[0])
        aggregate = json.loads((bench_dir / "mmlu_pro.aggregate.json").read_text(encoding="utf-8"))
        complete = json.loads((bench_dir / "mmlu_pro.complete.json").read_text(encoding="utf-8"))
        assert len(raw_lines) == 2
        assert len(scored_lines) == 2
        assert raw_record["record_type"] == "raw_result"
        assert scored_record["record_type"] == "scored_item"
        assert raw_record["payload_sha256"]
        assert scored_record["payload_sha256"]
        assert aggregate == record["benches"]["mmlu_pro"]
        assert complete["bench"] == "mmlu_pro"
        assert complete["raw_count"] == 2
        assert complete["scored_count"] == 2

    asyncio.run(scenario())


def test_partial_item_checkpoints_ignore_torn_line_and_exact_duplicates(tmp_path: Path) -> None:
    # Given: a checkpointed item, an exact duplicate append, and a torn final raw line.
    paths = campaign_paths(tmp_path / "campaign" / "localbench-run.json")
    raw_result = _raw_result("item-1", "Answer: A")
    scored_item = _scored_item("item-1", True)
    append_item_checkpoint(paths, "mmlu_pro", 0, "hash-1", raw_result, scored_item)
    append_item_checkpoint(paths, "mmlu_pro", 0, "hash-1", raw_result, scored_item)
    (paths.benchmarks_dir / "mmlu_pro.raw_results.jsonl").open("ab").write(b'{"record_type":"raw_result"')

    # When: partial item checkpoints are loaded for resume.
    checkpoints = read_partial_item_checkpoints(
        paths,
        "mmlu_pro",
        [ExpectedItemCheckpoint(seq=0, item_id="item-1", item_hash="hash-1")],
    )

    # Then: only the complete duplicate row is kept.
    assert len(checkpoints) == 1
    assert checkpoints[0].raw_result == raw_result
    assert checkpoints[0].scored_item == scored_item


def test_partial_item_checkpoints_reject_conflicting_duplicate(tmp_path: Path) -> None:
    # Given: two checkpoint rows for the same item identity with different payloads.
    paths = campaign_paths(tmp_path / "campaign" / "localbench-run.json")
    append_item_checkpoint(paths, "mmlu_pro", 0, "hash-1", _raw_result("item-1", "Answer: A"), _scored_item("item-1", True))
    append_item_checkpoint(paths, "mmlu_pro", 0, "hash-1", _raw_result("item-1", "Answer: B"), _scored_item("item-1", False))

    # When / Then: resume treats the duplicate as corruption.
    with pytest.raises(CheckpointCorruptionError):
        read_partial_item_checkpoints(
            paths,
            "mmlu_pro",
            [ExpectedItemCheckpoint(seq=0, item_id="item-1", item_hash="hash-1")],
        )


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


def test_run_localbench_resume_skips_checkpointed_items_mid_bench(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: a campaign interrupted after the first item checkpoint is flushed.
        output_path = tmp_path / "campaign" / "localbench-run.json"
        interrupted_requests: list[str] = []

        def interrupt_after_first_item(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
            prompt = json.loads(request.content)["messages"][0]["content"]
            interrupted_requests.append(prompt)
            if len(interrupted_requests) == 2:
                raise RuntimeError("worker killed")
            return _answer_a_handler(request)

        with pytest.raises(RuntimeError, match="worker killed"):
            await run_localbench(
                OrchestrateConfig(
                    endpoint="http://local/v1",
                    model="demo-model",
                    suite_dir=FIXTURE_SUITE,
                    bench="mmlu_pro",
                    max_items=2,
                    concurrency=1,
                    out=output_path,
                ),
                transport=httpx.MockTransport(interrupt_after_first_item),
            )

        resumed_requests: list[str] = []

        def answer_and_track_resume(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
            prompt = json.loads(request.content)["messages"][0]["content"]
            resumed_requests.append(prompt)
            return _answer_a_handler(request)

        # When: the campaign is resumed.
        resumed = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                max_items=2,
                concurrency=1,
                out=output_path,
                resume=tmp_path / "campaign",
            ),
            transport=httpx.MockTransport(answer_and_track_resume),
        )

        # Then: only the missing item is requested and a complete final artifact is assembled.
        assert len(interrupted_requests) == 2
        assert len(resumed_requests) == 1
        assert resumed_requests[0] == interrupted_requests[1]
        assert resumed["benches"]["mmlu_pro"]["n"] == 2
        assert [item["id"] for item in resumed["items"]] == ["1", "2"]
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


def _raw_result(item_id: str, response_text: str) -> dict:
    return {
        "id": item_id,
        "response_text": response_text,
        "reasoning_text": None,
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "latency_seconds": 0.01,
        "started_at": "2026-06-29T00:00:00+00:00",
        "finished_at": "2026-06-29T00:00:01+00:00",
        "attempts": 1,
        "error": None,
        "thinking_forced": False,
    }


def _scored_item(item_id: str, correct: bool) -> dict:
    return {
        "id": item_id,
        "bench": "mmlu_pro",
        "response_text": "Answer: A",
        "extracted": "A",
        "correct": correct,
        "finish_reason": "stop",
        "latency_seconds": 0.01,
        "started_at": "2026-06-29T00:00:00+00:00",
        "finished_at": "2026-06-29T00:00:01+00:00",
        "attempts": 1,
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "error": None,
    }

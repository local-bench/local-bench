from __future__ import annotations

import asyncio
import json
from datetime import datetime
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
from localbench.orchestrate import (
    OrchestrateConfig,
    UnsafeResumeError,
    _cumulative_run_timing,
    run_localbench,
)
from localbench.persistence import atomic_write_bytes, atomic_write_json

FIXTURE_SUITE = Path(__file__).parent / "fixtures" / "suite_v0"


def test_campaign_paths_derivations(tmp_path: Path) -> None:
    # localbench-run.json out: root is its parent, record stays at the given path.
    named = campaign_paths(tmp_path / "campaign" / "localbench-run.json")
    assert named.root == tmp_path / "campaign"
    assert named.final_run == tmp_path / "campaign" / "localbench-run.json"

    # .json out (the documented recipe shape): root is the suffix-stripped sibling dir.
    json_out = campaign_paths(tmp_path / "runs" / "my-run.json")
    assert json_out.root == tmp_path / "runs" / "my-run"
    assert json_out.final_run == tmp_path / "runs" / "my-run.json"

    # Extension-less out: MUST NOT collide root with final_run — that made the end-of-run
    # atomic rename target the campaign directory itself and lose the whole run.
    bare = campaign_paths(tmp_path / "runs" / "my-run")
    assert bare.root == tmp_path / "runs" / "my-run"
    assert bare.final_run == tmp_path / "runs" / "my-run" / "localbench-run.json"
    assert bare.root != bare.final_run


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


def test_partial_item_checkpoints_use_latest_record_across_segments(tmp_path: Path) -> None:
    # Given: an errored-then-retried item — same identity, different payloads, later segment.
    paths = campaign_paths(tmp_path / "campaign" / "localbench-run.json")
    append_item_checkpoint(paths, "mmlu_pro", 0, "hash-1", _raw_result("item-1", "Answer: A"), _scored_item("item-1", True))
    append_item_checkpoint(
        paths,
        "mmlu_pro",
        0,
        "hash-1",
        _raw_result("item-1", "Answer: B"),
        _scored_item("item-1", False),
        "segment-2",
    )

    # When: partial item checkpoints are loaded for resume.
    checkpoints = read_partial_item_checkpoints(
        paths,
        "mmlu_pro",
        [ExpectedItemCheckpoint(seq=0, item_id="item-1", item_hash="hash-1")],
    )

    # Then: append-only supersede uses the latest complete row.
    assert len(checkpoints) == 1
    assert checkpoints[0].raw_result["response_text"] == "Answer: B"
    assert checkpoints[0].scored_item is not None
    assert checkpoints[0].scored_item["correct"] is False


def test_partial_item_checkpoints_reject_same_segment_conflicting_duplicate(tmp_path: Path) -> None:
    # Given: two different payloads for the same item within one segment — a writer bug,
    # not a legitimate retry supersede.
    paths = campaign_paths(tmp_path / "campaign" / "localbench-run.json")
    append_item_checkpoint(paths, "mmlu_pro", 0, "hash-1", _raw_result("item-1", "Answer: A"), _scored_item("item-1", True))
    append_item_checkpoint(paths, "mmlu_pro", 0, "hash-1", _raw_result("item-1", "Answer: B"), _scored_item("item-1", False))

    # When / Then: resume fails closed instead of guessing which row to trust.
    with pytest.raises(CheckpointCorruptionError):
        read_partial_item_checkpoints(
            paths,
            "mmlu_pro",
            [ExpectedItemCheckpoint(seq=0, item_id="item-1", item_hash="hash-1")],
        )


def test_run_localbench_resume_skips_completed_benches_and_records_first_segment_bounds(
    tmp_path: Path,
) -> None:
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
        assert "segments" not in original
        first_segment = resumed["segments"][0]
        assert first_segment["started_at"] == min(item["started_at"] for item in original["items"])
        assert first_segment["finished_at"] == max(item["finished_at"] for item in original["items"])
        assert json.loads(output_path.read_text(encoding="utf-8")) == resumed

    asyncio.run(scenario())


def test_run_localbench_resume_reports_cumulative_wall_time(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def scenario() -> None:
        # Given: a completed first segment and a later one-hour resume segment.
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
        prior_started_at = min(item["started_at"] for item in original["items"])
        prior_finished_at = max(item["finished_at"] for item in original["items"])
        prior_wall_time = (
            datetime.fromisoformat(prior_finished_at) - datetime.fromisoformat(prior_started_at)
        ).total_seconds()
        resume_timestamps = iter(
            [
                "2099-01-01T00:00:00+00:00",
                "2099-01-01T01:00:00+00:00",
            ],
        )
        monkeypatch.setattr("localbench.orchestrate.utc_now", lambda: next(resume_timestamps))

        # When: the completed campaign is resumed without rerunning its items.
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
            transport=httpx.MockTransport(_answer_a_handler),
        )

        # Then: run bounds span both segments and wall time sums their active durations.
        expected_wall_time = prior_wall_time + 3600.0
        assert len(resumed["segments"]) == 2
        assert resumed["run_started_at"] == prior_started_at
        assert resumed["run_finished_at"] == "2099-01-01T01:00:00+00:00"
        assert resumed["totals"]["wall_time_seconds"] == pytest.approx(expected_wall_time)
        assert resumed["manifest"]["execution"]["wall_clock_s"] == pytest.approx(
            expected_wall_time,
        )

    asyncio.run(scenario())


def test_cumulative_run_timing_uses_item_durations_when_segment_bounds_are_unrecoverable() -> None:
    timing = _cumulative_run_timing(
        [
            {"segment_id": "segment-1", "started_at": None, "finished_at": None},
            {
                "segment_id": "segment-2",
                "started_at": "2026-07-22T10:00:00+00:00",
                "finished_at": "2026-07-22T10:01:00+00:00",
            },
        ],
        [
            {
                "id": "item-1",
                "started_at": "2026-07-22T00:00:00+00:00",
                "finished_at": "2026-07-22T00:02:00+00:00",
            },
            {
                "id": "item-2",
                "started_at": "2026-07-22T00:02:00+00:00",
                "finished_at": "2026-07-22T00:04:00+00:00",
            },
        ],
        fallback_started_at="2026-07-22T10:00:00+00:00",
        fallback_finished_at="2026-07-22T10:01:00+00:00",
        fallback_wall_clock_s=60.0,
    )

    assert timing.started_at == "2026-07-22T00:00:00+00:00"
    assert timing.finished_at == "2026-07-22T10:01:00+00:00"
    assert timing.wall_clock_s == 240.0


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


def test_run_localbench_resume_retry_errored_replans_only_error_items(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: a completed campaign whose latest record for item 2 is an errored non-measurement.
        output_path = tmp_path / "campaign" / "localbench-run.json"

        def fail_second_item(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
            prompt = json.loads(request.content)["messages"][0]["content"]
            if "Choose B" in prompt:
                return httpx.Response(500, text="server down")
            return _answer_a_handler(request)

        original = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                max_items=2,
                concurrency=1,
                out=output_path,
                server_fingerprint="fingerprint-a",
            ),
            transport=httpx.MockTransport(fail_second_item),
        )
        assert original["benches"]["mmlu_pro"]["n_errors"] == 1
        retried_prompts: list[str] = []

        def answer_and_track_retry(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
            prompt = json.loads(request.content)["messages"][0]["content"]
            retried_prompts.append(prompt)
            return _answer_a_handler(request)

        # When: resuming with retry-errored enabled.
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
                retry_errored=True,
                server_fingerprint="fingerprint-b",
            ),
            transport=httpx.MockTransport(answer_and_track_retry),
        )

        # Then: only the errored item is requested, the latest record wins, and resume history is honest.
        assert len(retried_prompts) == 1
        assert "Choose B" in retried_prompts[0]
        assert resumed["benches"]["mmlu_pro"]["n_errors"] == 0
        assert [item["error"] for item in resumed["items"]] == [None, None]
        assert resumed["resume_count"] == 1
        assert [segment["segment_id"] for segment in resumed["segments"]] == ["segment-1", "segment-2"]
        assert resumed["segments"][1]["server_fingerprint"] == "fingerprint-b"
        assert resumed["segments"][1]["completed_items"] == ["2"]
        raw_records = [
            json.loads(line)
            for line in (tmp_path / "campaign" / "benchmarks" / "mmlu_pro.raw_results.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert [record["segment_id"] for record in raw_records] == [
            "segment-1",
            "segment-1",
            "segment-2",
        ]

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

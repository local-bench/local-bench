"""Tests for v2-compatible run-record distribution fields."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from localbench.orchestrate import OrchestrateConfig, run_localbench
from localbench.run_schema import RUN_SCHEMA_VERSION, check_run_schema_version

FIXTURE_SUITE = Path(__file__).parent / "fixtures" / "suite_v0"


def test_run_record_includes_nullable_v2_submission_and_model_fields(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: a local run over one fixture item.
        output_path = tmp_path / "my-run.json"

        # When: the run record is written.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                max_items=1,
                out=output_path,
            ),
            transport=httpx.MockTransport(_handler_with_reasoning),
        )

        # Then: the run has explicit schema and v2-nullable distribution fields.
        check_run_schema_version(record)
        assert record["schema"] == "localbench-run-v0"
        assert record["schema_version"] == RUN_SCHEMA_VERSION
        assert record["submission_ticket_id"] is None
        assert record["server_nonce"] is None
        assert record["issued_at"] is None
        assert isinstance(record["run_started_at"], str)
        assert isinstance(record["run_finished_at"], str)
        assert record["source"] == "localbench-cli"
        assert record["tier"] == "quick"
        assert record["account"] is None
        assert record["model"] == {
            "name": "demo-model",
            "file_sha256": None,
            "tokenizer_digest": None,
            "chat_template_digest": None,
        }
        assert json.loads(output_path.read_text(encoding="utf-8")) == record

        # And: the per-item transcript shape keeps reasoning_text and finish_reason.
        item = record["items"][0]
        assert item["response_text"] == "Answer: A"
        assert item["reasoning_text"] == "chain of thought hidden by channel"
        assert item["finish_reason"] == "stop"

    asyncio.run(scenario())


def test_check_run_schema_version_rejects_missing_or_wrong_schema() -> None:
    # Given / When / Then: absent or stale schema versions are rejected.
    for record in ({}, {"schema_version": "old"}):
        try:
            check_run_schema_version(record)
        except ValueError as error:
            assert "schema_version" in str(error)
        else:
            raise AssertionError("schema version check should fail")


def _handler_with_reasoning(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": "Answer: A",
                        "reasoning_content": "chain of thought hidden by channel",
                    },
                    "finish_reason": "stop",
                },
            ],
            "usage": {
                "prompt_tokens": 7,
                "completion_tokens": 3,
                "total_tokens": 10,
            },
        },
    )

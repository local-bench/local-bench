"""Tests for v2-compatible run-record distribution fields."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from localbench.orchestrate import OrchestrateConfig, run_localbench
from localbench.run_schema import RUN_SCHEMA_VERSION, check_run_schema_version
from localbench.submissions.canon import sha256_file
from localbench.submissions.contracts import RESULT_BUNDLE_SCHEMA_VERSION

FIXTURE_SUITE = Path(__file__).parent / "fixtures" / "suite_v0"


def test_run_record_emits_result_bundle_v1_fields(tmp_path: Path) -> None:
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

        # Then: the run emits the split measurement-only result bundle contract.
        check_run_schema_version(record)
        assert RUN_SCHEMA_VERSION == RESULT_BUNDLE_SCHEMA_VERSION
        assert record["schema_version"] == RESULT_BUNDLE_SCHEMA_VERSION
        for removed in (
            "schema",
            "submission_ticket_id",
            "server_nonce",
            "issued_at",
            "account",
            "trust_tier",
            "serving_verification_level",
            "composite",
        ):
            assert removed not in record
        assert isinstance(record["run_started_at"], str)
        assert isinstance(record["run_finished_at"], str)
        assert record["producer"] == "localbench-cli"
        assert record["tier"] == "quick"
        assert record["serving_mode"] == "external_openai_compatible_endpoint"
        assert record["axis_status"]["schema_version"] == "localbench.axis-status.v1"
        assert record["headline_complete"] is False
        assert record["scores"]["headline_score"] is None
        assert record["scores"]["partial_composite_scope"] == "measured_headline_axes"
        assert record["scores"]["rank_scope"] == "custom-partial-v1"
        assert record["axis_status"]["axes"]["knowledge"] == {
            "axis": "knowledge",
            "status": "measured",
            "reason": "ok",
        }
        instruction_status = record["axis_status"]["axes"]["instruction_following"]
        assert instruction_status["status"] == "not_measured"
        assert instruction_status["reason"] == "not_run"
        assert record["model"] == {
            "name": "demo-model",
            "file_sha256": None,
            "tokenizer_digest": None,
            "chat_template_digest": None,
        }
        assert record["manifest"]["integrity"]["publishable"] is False
        assert record["manifest"]["integrity"]["blocking_reasons"] == [
            "sampler.top_k_unpinned",
            "sampler.seed_unpinned",
            "model.identity_missing",
            "runtime.identity_missing",
            "suite.not_site_released",
        ]
        assert "\\" not in record["output_path"]
        assert "/" not in record["output_path"]
        assert json.loads(output_path.read_text(encoding="utf-8")) == record

        # And: the per-item transcript shape keeps reasoning_text and finish_reason.
        item = record["items"][0]
        assert item["response_text"] == "Answer: A"
        assert item["reasoning_text"] == "chain of thought hidden by channel"
        assert item["finish_reason"] == "stop"

    asyncio.run(scenario())


def test_axis_status_is_additive_to_existing_run_record_fields(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: a local run with deterministic existing field values.
        output_path = tmp_path / "my-run.json"

        # When: the run record is written with the additive axis_status block.
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
        written = json.loads(output_path.read_text(encoding="utf-8"))

        # Then: removing axis_status leaves the pre-existing top-level contract untouched.
        result_bundle_keys = (
            "schema_version",
            "run_started_at",
            "run_finished_at",
            "producer",
            "tier",
            "serving_mode",
            "model",
            "manifest",
            "headline_complete",
            "scores",
            "benches",
            "conformance",
            "items",
            "totals",
            "warnings",
            "output_path",
        )
        assert tuple(key for key in record if key != "axis_status") == result_bundle_keys
        assert {key: written[key] for key in result_bundle_keys} == {
            key: record[key] for key in result_bundle_keys
        }

    asyncio.run(scenario())


def test_publishable_lane_pins_sampler_and_records_identity(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: a publishable-lane local run with explicit artifact and runtime identity.
        output_path = tmp_path / "publishable-run.json"
        model_file = tmp_path / "model.gguf"
        tokenizer_file = tmp_path / "tokenizer.json"
        chat_template_file = tmp_path / "chat-template.jinja"
        model_file.write_bytes(b"model-bytes")
        tokenizer_file.write_bytes(b"tokenizer-bytes")
        chat_template_file.write_bytes(b"template-bytes")
        chat_payloads: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "demo-model"}]})
            chat_payloads.append(json.loads(request.content.decode("utf-8")))
            return _handler_with_reasoning(request)

        # When: the runner uses the publishable lane.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                max_items=1,
                out=output_path,
                publishable=True,
                sampler_temperature=0,
                sampler_top_k=1,
                sampler_top_p=1,
                sampler_min_p=0,
                sampler_seed=123,
                determinism_policy="top_k_1_seeded",
                model_file=model_file,
                model_family="gemma",
                quant_label="Q4_K_M",
                model_format="gguf",
                tokenizer_file=tokenizer_file,
                chat_template_file=chat_template_file,
                tokenizer_digest_source="external.file",
                chat_template_digest_source="server.override",
                runtime_name="llama.cpp",
                runtime_version="b1234",
                kv_cache_quant="q8_0",
                ctx_len_configured=8192,
                parallel_slots=1,
                build_flags="cuda",
                runner_build_id="runner-20260630",
            ),
            transport=httpx.MockTransport(handler),
        )

        # Then: sampler pins are present in both request payload and manifest.
        assert chat_payloads[0]["top_k"] == 1
        assert chat_payloads[0]["top_p"] == 1
        assert chat_payloads[0]["min_p"] == 0
        assert chat_payloads[0]["seed"] == 123
        sampling = record["manifest"]["sampling"]
        assert sampling["temperature"] == 0
        assert sampling["top_k"] == 1
        assert sampling["top_p"] == 1
        assert sampling["min_p"] == 0
        assert sampling["seed"] == 123
        assert sampling["determinism_policy"] == "top_k_1_seeded"

        # And: model/runtime identity fields are filled, leaving only suite release blocking.
        manifest_model = record["manifest"]["model"]
        assert manifest_model == {
            "family": "gemma",
            "quant_label": "Q4_K_M",
            "file_name": "model.gguf",
            "file_size_bytes": len(b"model-bytes"),
            "file_sha256": sha256_file(model_file),
            "format": "gguf",
            "tokenizer_digest": sha256_file(tokenizer_file),
            "tokenizer_digest_source": "external.file",
            "chat_template_digest": sha256_file(chat_template_file),
            "chat_template_digest_source": "server.override",
        }
        assert record["manifest"]["runtime"] == {
            "name": "llama.cpp",
            "version": "b1234",
            "kv_cache_quant": "q8_0",
            "ctx_len_configured": 8192,
            "parallel_slots": 1,
            "build_flags": "cuda",
        }
        assert record["manifest"]["integrity"]["blocking_reasons"] == ["suite.not_site_released"]
        assert record["manifest"]["integrity"]["missing_required_fields"] == []

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

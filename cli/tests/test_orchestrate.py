"""Tests for the localbench benchmark orchestrator."""

from __future__ import annotations

import asyncio
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from localbench.cli import (
    EndpointPreflightError,
    _preflight_endpoint,
    _preflight_server_context,
    _preflight_smoke,
)
from localbench.orchestrate import OrchestrateConfig, run_localbench
from localbench.suite_resolver import SuiteResolutionError


FIXTURE_SUITE = Path(__file__).parent / "fixtures" / "suite_v0"
FIXTURE_FULL_BENCHES = "mmlu_pro,ifeval,genmath"


def test_run_localbench_when_fixture_suite_scores_and_writes_json(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given a fixture suite and an OpenAI-compatible endpoint with mixed outcomes.
        output_path = tmp_path / "run.json"
        transport = httpx.MockTransport(_mixed_handler)

        # When running every fixture bench through the orchestrator.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench=FIXTURE_FULL_BENCHES,
                out=output_path,
                price_in=1.0,
                price_out=2.0,
            ),
            transport=transport,
        )

        # Then the JSON contract, aggregates, manifest, and pricing are written.
        assert record["schema_version"] == "localbench.result_bundle.v1"
        assert json.loads(output_path.read_text(encoding="utf-8")) == record
        assert len(record["items"]) == 7
        assert record["benches"]["mmlu_pro"] == {
            "n": 3,
            "n_errors": 0,
            "n_extraction_failures": 1,
            "raw_accuracy": pytest.approx(1 / 3),
            "chance_corrected": pytest.approx(1 / 9),
            "termination_rate": 1.0,
            "conditional_accuracy": pytest.approx(1 / 3),
        }
        assert record["benches"]["ifeval"] == {
            "n": 2,
            "n_errors": 1,
            "n_extraction_failures": 0,
            "raw_accuracy": 0.5,
            "chance_corrected": 0.5,
            "termination_rate": 0.5,
            "conditional_accuracy": 1.0,
        }
        assert record["benches"]["genmath"] == {
            "n": 2,
            "n_errors": 0,
            "n_extraction_failures": 0,
            "raw_accuracy": 0.5,
            "chance_corrected": 0.5,
            "termination_rate": 1.0,
            "conditional_accuracy": 0.5,
        }
        # Composite is HEADLINE-only: knowledge, instruction, and math are measured here.
        assert record["scores"]["partial_composite"] == pytest.approx(
            0.3333,
        )
        assert record["totals"]["prompt_tokens"] == 50
        assert record["totals"]["completion_tokens"] == 14
        assert record["totals"]["total_tokens"] == 64
        assert record["estimated_cost_usd"] == pytest.approx(0.000078)
        assert record["manifest"]["endpoint"]["runtime_reported_model"] == "runtime-demo"
        assert record["manifest"]["suite"]["item_set_hashes"] == {
            "genmath_quick.jsonl": "2550942dd15a44f48e574d83d9c2bec559a56b128e51fa9197c44146f93fa976",
            "ifeval_quick.jsonl": "759ea4ebb17ff571ae98e3fdd0b612d382021e062aa945e6d001faae2985e707",
            "mmlu_pro_quick.jsonl": "685cfe3985469d26eecff4fc4a0aaa6c31e1f1a0f070a86074c9b388119ac0ac",
        }
        assert record["manifest"]["integrity"]["publishable"] is False

    asyncio.run(scenario())


def test_run_localbench_when_max_items_truncates_each_bench(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given a fixture suite with multiple items in each bench.
        output_path = tmp_path / "run.json"

        # When limiting each bench to one item.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench=FIXTURE_FULL_BENCHES,
                lane="bounded-final-v1",
                out=output_path,
                max_items=1,
            ),
            transport=httpx.MockTransport(_all_correct_handler),
        )

        # Then each bench contributes only its first item.
        assert [item["id"] for item in record["items"]] == ["1", "11", "math-1"]
        assert record["benches"]["mmlu_pro"]["n"] == 1
        assert record["benches"]["ifeval"]["n"] == 1
        assert record["benches"]["genmath"]["n"] == 1
        assert record["suite_coverage"]["status"] == "partial"
        assert record["suite_coverage"]["covered_items"] == 3
        assert record["suite_coverage"]["total_items"] == 7
        assert record["suite_coverage"]["max_items_truncated"] is True

    asyncio.run(scenario())


def test_perf_capture_does_not_change_scorecard_identity(tmp_path: Path) -> None:
    async def scenario() -> None:
        timings = {"prompt_n": 10, "prompt_ms": 20.0, "predicted_n": 4, "predicted_ms": 16.0}

        def timed_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
            payload = json.loads(request.content)
            prompt = payload["messages"][0]["content"]
            if "Choose the first letter" in prompt:
                return _completion("Answer: A", 1, 1, timings=timings)
            return httpx.Response(500, text="unexpected prompt")

        plain_record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                out=tmp_path / "plain.json",
                max_items=1,
            ),
            transport=httpx.MockTransport(_all_correct_handler),
        )
        timed_record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                out=tmp_path / "timed.json",
                max_items=1,
            ),
            transport=httpx.MockTransport(timed_handler),
        )

        assert plain_record["manifest"]["scorecard"]["scorecard_id"] == (
            timed_record["manifest"]["scorecard"]["scorecard_id"]
        )
        assert plain_record["items"][0]["server_timings"] is None
        assert timed_record["items"][0]["server_timings"] == {"passes": [timings]}
        assert timed_record["perf"]["timings_coverage"] == 1.0
        assert timed_record["perf"]["prefill_tps"] == pytest.approx(500.0)
        assert timed_record["perf"]["decode_tps"] == pytest.approx(250.0)

    asyncio.run(scenario())


def test_run_localbench_when_item_file_is_missing_fails_closed(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given a suite entry whose item file does not exist.
        suite_dir = tmp_path / "suite"
        suite_dir.mkdir()
        (suite_dir / "suite.json").write_text(
            json.dumps(
                {
                    "version": "suite-fixture-v0",
                    "benches": {
                        "genmath": {
                            "chance_correction_baseline": 0.0,
                            "decoding": {"max_tokens": 8, "temperature": 0},
                            "itemsets": {"quick": {"file": "missing.jsonl"}},
                            "template": "templates/genmath.txt",
                        },
                    },
                },
            ),
            encoding="utf-8",
        )
        (suite_dir / "itemsets.lock.json").write_text('{"files": {}}', encoding="utf-8")
        (suite_dir / "templates").mkdir()
        (suite_dir / "templates" / "genmath.txt").write_text("{statement}", encoding="utf-8")

        # When / Then: the suite verifier stops before a run can begin.
        with pytest.raises(SuiteResolutionError, match="itemsets.lock.json"):
            await run_localbench(
                OrchestrateConfig(
                    endpoint="http://local/v1",
                    model="demo-model",
                    suite_dir=suite_dir,
                    bench="genmath",
                    out=tmp_path / "run.json",
                ),
                transport=httpx.MockTransport(_all_correct_handler),
            )

    asyncio.run(scenario())


def test_cli_run_help_exits_zero() -> None:
    # Given the module CLI entry point.
    # When requesting run help.
    result = subprocess.run(
        [sys.executable, "-m", "localbench", "run", "--help"],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    # Then argparse exits successfully and shows run options.
    assert result.returncode == 0
    assert "--endpoint" in result.stdout
    assert "--provider" in result.stdout
    assert "--reasoning-effort" in result.stdout
    assert "--hf-model-id" in result.stdout
    assert "--reasoning-activation" in result.stdout


def test_cli_run_when_endpoint_is_missing_exits_two() -> None:
    # Given the module CLI entry point.
    # When running without the required endpoint.
    result = subprocess.run(
        [sys.executable, "-m", "localbench", "run", "--model", "demo-model"],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    # Then the parser returns a clean usage error.
    assert result.returncode == 2
    assert "--endpoint" in result.stderr


def test_preflight_endpoint_requires_claimed_model() -> None:
    async def scenario() -> None:
        # Given: an OpenAI-compatible models endpoint that omits the requested model.
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/models"
            return httpx.Response(200, json={"data": [{"id": "other-model"}]})

        # When / Then: preflight refuses before any benchmark campaign starts.
        with pytest.raises(EndpointPreflightError, match="demo-model"):
            await _preflight_endpoint(
                "http://local/v1",
                "demo-model",
                transport=httpx.MockTransport(handler),
            )

    asyncio.run(scenario())


def test_preflight_server_context_reads_llama_props_at_server_root() -> None:
    async def scenario() -> None:
        # Given: llama.cpp exposes total context and two parallel slots at server-root /props.
        seen_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            return httpx.Response(
                200,
                json={
                    "default_generation_settings": {"n_ctx": 65536},
                    "total_slots": 2,
                },
            )

        # When: a publishable bounded-final endpoint preflight probes context.
        observed = await _preflight_server_context(
            "http://local/v1",
            lane="bounded-final-v2",
            publishable=True,
            ctx_len_configured=None,
            transport=httpx.MockTransport(handler),
        )

        # Then: /v1 is stripped, and the per-slot context is derived from total/slots.
        assert seen_paths == ["/props"]
        assert observed == 32768

    asyncio.run(scenario())


def test_preflight_server_context_rejects_small_llama_context() -> None:
    async def scenario() -> None:
        # Given: llama.cpp reports less than the ranked bounded-final context floor.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "default_generation_settings": {"n_ctx": 16384},
                    "total_slots": 1,
                },
            )

        # When / Then: preflight fails with the observed value and corrected llama-server flag.
        with pytest.raises(
            EndpointPreflightError,
            match=r"probed server context 16384.*required 32768.*--ctx-size 32768",
        ):
            await _preflight_server_context(
                "http://local/v1",
                lane="bounded-final-v2",
                publishable=True,
                ctx_len_configured=None,
                transport=httpx.MockTransport(handler),
            )

    asyncio.run(scenario())


def test_preflight_server_context_requires_configured_ctx_when_unverified(
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def scenario() -> None:
        # Given: a non-llama.cpp endpoint does not expose a recognizable /props payload.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": "not found"})

        # When / Then: publishable bounded-final requires explicit user-declared context.
        with pytest.raises(EndpointPreflightError, match="--ctx-len-configured"):
            await _preflight_server_context(
                "http://local/v1",
                lane="bounded-final-v2",
                publishable=True,
                ctx_len_configured=None,
                transport=httpx.MockTransport(handler),
            )

    asyncio.run(scenario())
    output = capsys.readouterr().out
    assert "warning    server context could not be verified; ensure >= 32768" in output


def test_preflight_server_context_rejects_small_configured_ctx_when_unverified(
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def scenario() -> None:
        # Given: a non-llama.cpp endpoint does not expose a /props context.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": "not found"})

        # When / Then: an undersized user-declared context fails closed.
        with pytest.raises(
            EndpointPreflightError,
            match=(
                r"declared context 8192 is too small for publishable bounded-final-v2; "
                r"restart the server with a >= 32768 context and pass the true value"
            ),
        ):
            await _preflight_server_context(
                "http://local/v1",
                lane="bounded-final-v2",
                publishable=True,
                ctx_len_configured=8192,
                transport=httpx.MockTransport(handler),
            )

    asyncio.run(scenario())
    output = capsys.readouterr().out
    assert "warning    server context could not be verified; ensure >= 32768" in output


def test_preflight_server_context_accepts_floor_configured_ctx_when_unverified(
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def scenario() -> None:
        # Given: a non-llama.cpp endpoint does not expose a /props context.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": "not found"})

        # When: the declared context satisfies the publishable bounded-final floor.
        observed = await _preflight_server_context(
            "http://local/v1",
            lane="bounded-final-v2",
            publishable=True,
            ctx_len_configured=32768,
            transport=httpx.MockTransport(handler),
        )

        # Then: preflight allows the run while leaving observed context unknown.
        assert observed is None

    asyncio.run(scenario())
    output = capsys.readouterr().out
    assert "warning    server context could not be verified; ensure >= 32768" in output


def test_preflight_server_context_skips_probe_when_not_publishable() -> None:
    async def scenario() -> None:
        # Given: a non-publishable bounded-final run.
        def unexpected_request(request: httpx.Request) -> httpx.Response:
            raise AssertionError(f"unexpected probe to {request.url}")

        # When: server context preflight runs.
        observed = await _preflight_server_context(
            "http://local/v1",
            lane="bounded-final-v2",
            publishable=False,
            ctx_len_configured=8192,
            transport=httpx.MockTransport(unexpected_request),
        )

        # Then: it does not probe /props or enforce publishable-only context rules.
        assert observed is None

    asyncio.run(scenario())


def test_preflight_server_context_rejects_configured_ctx_mismatch() -> None:
    async def scenario() -> None:
        # Given: the declared context is more than five percent above the probed context.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "default_generation_settings": {"n_ctx": 32768},
                    "total_slots": 1,
                },
            )

        # When / Then: preflight refuses the mismatch.
        with pytest.raises(
            EndpointPreflightError,
            match=r"--ctx-len-configured 40960 disagrees with probed server context 32768",
        ):
            await _preflight_server_context(
                "http://local/v1",
                lane="bounded-final-v2",
                publishable=True,
                ctx_len_configured=40960,
                transport=httpx.MockTransport(handler),
            )

    asyncio.run(scenario())


def test_run_threads_observed_context_to_orchestrate_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: endpoint preflight observes a 32768-token context.
    import localbench.cli as cli_mod

    captured_configs: list[OrchestrateConfig] = []

    async def fake_preflight_endpoint(*_args: object, **_kwargs: object) -> None:
        return None

    async def fake_preflight_smoke(*_args: object, **_kwargs: object) -> None:
        return None

    async def fake_preflight_context(*_args: object, **_kwargs: object) -> int:
        return 32768

    async def fake_run_localbench(config: OrchestrateConfig, **_kwargs: object) -> dict[str, object]:
        captured_configs.append(config)
        return {"benches": {}, "totals": {}, "warnings": []}

    monkeypatch.setattr(cli_mod, "_preflight_endpoint", fake_preflight_endpoint)
    monkeypatch.setattr(cli_mod, "_preflight_smoke", fake_preflight_smoke)
    monkeypatch.setattr(cli_mod, "_preflight_server_context", fake_preflight_context)
    monkeypatch.setattr(cli_mod, "run_localbench", fake_run_localbench)
    monkeypatch.setattr(cli_mod, "_print_summary", lambda record, out=None: None)

    # When: a publishable bounded-final endpoint run passes preflight.
    code = cli_mod.main(
        [
            "run",
            "--endpoint",
            "http://local/v1",
            "--model",
            "demo-model",
            "--suite-dir",
            str(FIXTURE_SUITE),
            "--bench",
            "mmlu_pro",
            "--lane",
            "bounded-final-v2",
            "--publishable",
            "--sampler-seed",
            "1234",
            "--gguf-repo-only",
            "--ctx-len-configured",
            "32768",
            "--no-supervisor",
        ],
    )

    # Then: the observed context reaches the final run record writer.
    assert code == 0
    assert captured_configs[-1].ctx_len_observed == 32768


def test_preflight_smoke_runs_one_item_per_bench_without_real_output(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: a full run request covering two benches.
        requested_prompts: list[str] = []
        out = tmp_path / "campaign" / "localbench-run.json"
        args = argparse.Namespace(
            endpoint="http://local/v1",
            model="demo-model",
            suite=FIXTURE_SUITE.name,
            suite_dir=FIXTURE_SUITE,
            suite_source=None,
            accept_suite_terms=False,
            cache_dir=None,
            concurrency=2,
            out=out,
            max_items=2,
            price_in=None,
            price_out=None,
            lane="answer-only",
            provider="local",
            reasoning_effort=None,
            hf_model_id=None,
            reasoning_activation="qwen3",
            max_tokens=None,
            resume=None,
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "demo-model"}]})
            requested_prompts.append(json.loads(request.content)["messages"][0]["content"])
            return _all_correct_handler(request)

        # When: the smoke preflight runs.
        await _preflight_smoke(
            args,
            "quick",
            api_key=None,
            bench_choice="mmlu_pro,genmath",
            transport=httpx.MockTransport(handler),
        )

        # Then: it exercises one item per selected bench and does not write the real output.
        assert len(requested_prompts) == 2
        assert not out.exists()

    asyncio.run(scenario())


def test_run_localbench_failure_status_includes_resume_hint(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: an endpoint that fails after one completed item checkpoint.
        output_path = tmp_path / "campaign" / "localbench-run.json"
        requests = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal requests
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "demo-model"}]})
            requests += 1
            if requests == 2:
                raise RuntimeError("worker stopped")
            return _all_correct_handler(request)

        # When / Then: failure status captures resumable context.
        with pytest.raises(RuntimeError, match="worker stopped"):
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
                transport=httpx.MockTransport(handler),
            )
        status = json.loads((tmp_path / "campaign" / "run.status.json").read_text(encoding="utf-8"))
        assert status["state"] == "failed"
        assert status["completed_items"] == 1
        assert status["last_completed_item_id"] == "1"
        assert "worker stopped" in status["failure_reason"]
        assert status["resume_hint"] == f"localbench run --resume {tmp_path / 'campaign'}"
        assert status["stderr_tail"] == []
        assert status["serve_log_tail"] == []
        assert status["monitor_snapshot"] is None

    asyncio.run(scenario())


def test_run_localbench_trips_server_unreachable_breaker_after_three_connection_items(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        # Given: a serve-style single-concurrency campaign whose endpoint dies after one item.
        output_path = tmp_path / "campaign" / "localbench-run.json"
        item_requests = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal item_requests
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
            item_requests += 1
            if item_requests == 1:
                return _completion("Answer: A", 1, 1)
            raise httpx.ConnectError("connection refused", request=request)

        # When / Then: the campaign stops after three consecutive connection-class item failures.
        with pytest.raises(RuntimeError, match="server_unreachable_circuit_breaker"):
            await run_localbench(
                OrchestrateConfig(
                    endpoint="http://local/v1",
                    model="demo-model",
                    suite_dir=FIXTURE_SUITE,
                    bench=FIXTURE_FULL_BENCHES,
                    concurrency=1,
                    out=output_path,
                ),
                transport=httpx.MockTransport(handler),
            )

        status = json.loads((tmp_path / "campaign" / "run.status.json").read_text(encoding="utf-8"))
        benchmark_dir = tmp_path / "campaign" / "benchmarks"
        scored_records = [
            json.loads(line)
            for path in sorted(benchmark_dir.glob("*.scored_items.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        assert status["state"] == "failed"
        assert status["failure_reason"] == "server_unreachable_circuit_breaker"
        assert status["exit_code"] == 70
        assert status["completed_items"] == 4
        error_flags = [record["payload"]["error"] is not None for record in scored_records]
        assert len(error_flags) == 4
        assert error_flags.count(True) == 3
        assert any(record["payload"]["id"] == "1" and record["payload"]["error"] is None for record in scored_records)
        assert not (benchmark_dir / "genmath.raw_results.jsonl").exists()

    asyncio.run(scenario())


def test_run_localbench_does_not_trip_breaker_for_scattered_connection_errors(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        # Given: connection-class item failures separated by successful measurements.
        output_path = tmp_path / "campaign" / "localbench-run.json"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
            prompt = json.loads(request.content)["messages"][0]["content"]
            if "Choose B" in prompt or "JSON object with key ok" in prompt:
                raise httpx.ConnectError("connection refused", request=request)
            return _completion("Answer: A", 1, 1)

        # When: the campaign has connection errors, but never three consecutive item failures.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench=FIXTURE_FULL_BENCHES,
                concurrency=1,
                out=output_path,
            ),
            transport=httpx.MockTransport(handler),
        )

        # Then: the run completes and keeps the connection errors as item-level non-measurements.
        status = json.loads((tmp_path / "campaign" / "run.status.json").read_text(encoding="utf-8"))
        assert status["state"] == "complete"
        assert status["failure_reason"] is None
        assert sum(1 for item in record["items"] if item["error"] is not None) == 2

    asyncio.run(scenario())


def test_run_localbench_lane_controls_thinking_toggle(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given a handler that captures every chat-completion request body.
        captured: list[dict] = []

        def capturing_handler(request: httpx.Request) -> httpx.Response:
            if not request.url.path.endswith("/models"):
                captured.append(json.loads(request.content))
            return _all_correct_handler(request)

        # When running in the default answer-only lane.
        await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench=FIXTURE_FULL_BENCHES,
                out=tmp_path / "answer_only.json",
            ),
            transport=httpx.MockTransport(capturing_handler),
        )

        # Then every request disables Qwen3-family thinking.
        assert captured
        assert all(
            payload["chat_template_kwargs"] == {"enable_thinking": False}
            for payload in captured
        )

        # When running in the api-uncapped lane.
        captured.clear()
        await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench=FIXTURE_FULL_BENCHES,
                out=tmp_path / "uncapped.json",
                lane="api-uncapped",
            ),
            transport=httpx.MockTransport(capturing_handler),
        )

        # Then the local-only field is never sent to API-style endpoints.
        assert captured
        assert all("chat_template_kwargs" not in payload for payload in captured)

    asyncio.run(scenario())


def test_bounded_final_publishable_answer_only_accepts_arbitrary_model_id(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        captured: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if not request.url.path.endswith("/models"):
                captured.append(json.loads(request.content))
            return _all_correct_handler(request)

        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="unranked-family-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                out=tmp_path / "bounded.json",
                max_items=1,
                lane="bounded-final-v1",
                publishable=True,
                model_family="arbitrary-new-family",
                sampler_temperature=0.0,
                sampler_top_k=1,
                sampler_seed=1234,
                determinism_policy="strict-greedy-temp0-seeded-v1",
            ),
            transport=httpx.MockTransport(handler),
        )

        assert captured
        assert captured[0]["max_tokens"] == 32
        assert captured[0]["chat_template_kwargs"] == {"enable_thinking": False}
        assert "think_budget" not in captured[0]
        assert record["manifest"]["suite"]["lane"] == "bounded-final-v1"
        assert record["manifest"]["scorecard"]["lane_spec_id"] == "bounded-final-v1"
        assert record["manifest"]["sampling"]["execution_profile_id"] == "answer_only_v1"
        assert record["manifest"]["execution_profile"]["id"] == "answer_only_v1"
        assert record["budget_audit"]["status"] == "exact"
        assert record["items"][0]["generated_tokens"] == {
            "total": 1,
            "reasoning": 0,
            "final": 1,
            "source": "server_usage",
        }

    asyncio.run(scenario())


def test_bounded_final_publishable_user_stop_is_diagnostic_only(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        suite_dir = tmp_path / "suite"
        shutil.copytree(FIXTURE_SUITE, suite_dir)
        suite_json = json.loads((suite_dir / "suite.json").read_text(encoding="utf-8"))
        suite_json["benches"]["mmlu_pro"]["decoding"]["stop"] = ["END"]
        (suite_dir / "suite.json").write_text(json.dumps(suite_json), encoding="utf-8")
        captured: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if not request.url.path.endswith("/models"):
                captured.append(json.loads(request.content))
            return _all_correct_handler(request)

        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=suite_dir,
                bench="mmlu_pro",
                out=tmp_path / "bounded-stop.json",
                max_items=1,
                lane="bounded-final-v1",
                publishable=True,
                sampler_temperature=0.0,
                sampler_top_k=1,
                sampler_seed=1234,
                determinism_policy="strict-greedy-temp0-seeded-v1",
            ),
            transport=httpx.MockTransport(handler),
        )

        assert captured
        assert "stop" not in captured[0]
        assert record["prompt_audit"]["status"] == "diagnostic-only"
        assert any("user-supplied stop" in warning for warning in record["warnings"])

    asyncio.run(scenario())


def test_bounded_final_budget_audit_unverified_when_usage_is_missing(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
            return _completion_without_usage("Answer: A")

        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                out=tmp_path / "bounded-unverified.json",
                max_items=1,
                lane="bounded-final-v1",
                publishable=True,
                sampler_temperature=0.0,
                sampler_top_k=1,
                sampler_seed=1234,
                determinism_policy="strict-greedy-temp0-seeded-v1",
            ),
            transport=httpx.MockTransport(handler),
        )

        assert record["budget_audit"]["status"] == "unverified"
        assert "generated_tokens" not in record["items"][0]

    asyncio.run(scenario())


def test_run_localbench_builds_hf_renderer_once_for_capped_thinking_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CountingRenderer:
        def __init__(self) -> None:
            self.render_count = 0

        def render(self, messages: list[dict[str, str]]) -> str:
            self.render_count += 1
            return "<custom-assistant>\n"

    async def scenario() -> None:
        # Given a local capped-thinking run over multiple benches with an HF model id.
        renderer = CountingRenderer()
        build_calls: list[tuple[str | None, str]] = []

        def build_renderer(hf_model_id: str | None, activation: str) -> CountingRenderer:
            build_calls.append((hf_model_id, activation))
            return renderer

        monkeypatch.setattr("localbench.orchestrate.build_forced_prompt_renderer", build_renderer)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
            payload = json.loads(request.content)
            if payload["stop"] == ["</think>"]:
                return _raw_completion("<think>\nreasoning", "length", 1, 8)
            return _raw_completion("Answer: A", "stop", 1, 1)

        # When the orchestrator executes the per-bench runner calls.
        await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                out=tmp_path / "capped.json",
                bench="mmlu_pro,ifeval",
                max_items=1,
                lane="capped-thinking",
                hf_model_id="ibm-granite/granite-3.3-8b-instruct",
                reasoning_activation="granite",
            ),
            transport=httpx.MockTransport(handler),
        )

        # Then tokenizer/renderer construction is once per run config, not once per bench.
        assert build_calls == [("ibm-granite/granite-3.3-8b-instruct", "granite")]
        assert renderer.render_count == 2

    asyncio.run(scenario())


def test_publishable_capped_thinking_rejects_family_mismatch(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: a publishable Gemma-family run is misconfigured with Qwen activation.
        def unexpected_request(request: httpx.Request) -> httpx.Response:
            raise AssertionError(f"unexpected request: {request.url}")

        # When / Then: orchestration fails closed before any request is sent.
        with pytest.raises(
            RuntimeError,
            match=r"model family 'gemma4'.*activation 'qwen3'.*qwen_thinking_native_v1",
        ):
            await run_localbench(
                OrchestrateConfig(
                    endpoint="http://local/v1",
                    model="demo-model",
                    suite_dir=FIXTURE_SUITE,
                    out=tmp_path / "mismatch.json",
                    bench="mmlu_pro",
                    max_items=1,
                    lane="capped-thinking",
                    publishable=True,
                    model_family="gemma4",
                    hf_model_id="unsloth/gemma-4-12b-it",
                    reasoning_activation="qwen3",
                ),
                transport=httpx.MockTransport(unexpected_request),
            )

    asyncio.run(scenario())


def test_publishable_capped_thinking_accepts_matching_gemma_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CountingRenderer:
        def __init__(self) -> None:
            self.render_count = 0

        def render(self, messages: list[dict[str, str]]) -> str:
            self.render_count += 1
            return "<gemma-assistant>\n"

    async def scenario() -> None:
        # Given: a publishable Gemma-family capped-thinking run with an HF renderer configured.
        renderer = CountingRenderer()
        build_calls: list[tuple[str | None, str]] = []

        def build_renderer(hf_model_id: str | None, activation: str) -> CountingRenderer:
            build_calls.append((hf_model_id, activation))
            return renderer

        monkeypatch.setattr("localbench.orchestrate.build_forced_prompt_renderer", build_renderer)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
            payload = json.loads(request.content)
            if payload["stop"] == ["<channel|>"]:
                return _raw_completion("<|channel>thought\nreasoning", "length", 1, 8)
            return _raw_completion("Answer: A<turn|>", "stop", 1, 1)

        # When: the orchestrator executes the publishable capped-thinking run.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                out=tmp_path / "gemma.json",
                bench="mmlu_pro",
                max_items=1,
                lane="capped-thinking",
                publishable=True,
                model_family="gemma4",
                hf_model_id="unsloth/gemma-4-12b-it",
                reasoning_activation="gemma4",
            ),
            transport=httpx.MockTransport(handler),
        )

        # Then: the guard allows the run and records the resolved Gemma registry entry.
        assert build_calls == [("unsloth/gemma-4-12b-it", "gemma4")]
        assert renderer.render_count == 1
        assert record["manifest"]["sampling"]["execution_profile_id"] == (
            "gemma4_thinking_native_v1"
        )

    asyncio.run(scenario())


def test_publishable_capped_thinking_requires_hf_model_id(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: a publishable capped-thinking run has no HF model id.
        def unexpected_request(request: httpx.Request) -> httpx.Response:
            raise AssertionError(f"unexpected request: {request.url}")

        # When / Then: orchestration fails before the ChatML fallback renderer can be used.
        with pytest.raises(
            RuntimeError,
            match=r"publishable capped-thinking requires --hf-model-id",
        ):
            await run_localbench(
                OrchestrateConfig(
                    endpoint="http://local/v1",
                    model="demo-model",
                    suite_dir=FIXTURE_SUITE,
                    out=tmp_path / "missing-hf.json",
                    bench="mmlu_pro",
                    max_items=1,
                    lane="capped-thinking",
                    publishable=True,
                    model_family="gemma4",
                    reasoning_activation="gemma4",
                ),
                transport=httpx.MockTransport(unexpected_request),
            )

    asyncio.run(scenario())


def test_publishable_capped_thinking_rejects_unranked_activation(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: a publishable capped-thinking run requests an activation without a ranked entry.
        def unexpected_request(request: httpx.Request) -> httpx.Response:
            raise AssertionError(f"unexpected request: {request.url}")

        # When / Then: orchestration refuses the unranked registry configuration.
        with pytest.raises(
            RuntimeError,
            match=r"no ranked reasoning-registry entry.*granite",
        ):
            await run_localbench(
                OrchestrateConfig(
                    endpoint="http://local/v1",
                    model="demo-model",
                    suite_dir=FIXTURE_SUITE,
                    out=tmp_path / "granite.json",
                    bench="mmlu_pro",
                    max_items=1,
                    lane="capped-thinking",
                    publishable=True,
                    hf_model_id="ibm-granite/granite-3.3-8b-instruct",
                    reasoning_activation="granite",
                ),
                transport=httpx.MockTransport(unexpected_request),
            )

    asyncio.run(scenario())


def test_non_publishable_capped_thinking_keeps_default_diagnostic_renderer(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: a non-publishable capped-thinking diagnostic run uses the legacy defaults.
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
            payload = json.loads(request.content)
            if payload["stop"] == ["</think>"]:
                return _raw_completion("<think>\nreasoning", "length", 1, 8)
            return _raw_completion("Answer: A", "stop", 1, 1)

        # When: the run executes without publishable integrity constraints.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                out=tmp_path / "diagnostic.json",
                bench="mmlu_pro",
                max_items=1,
                lane="capped-thinking",
            ),
            transport=httpx.MockTransport(handler),
        )

        # Then: back-compat keeps the Qwen fallback path available for diagnostics.
        assert record["manifest"]["integrity"]["publishable"] is False
        assert record["manifest"]["sampling"]["execution_profile_id"] == (
            "qwen_thinking_native_v1"
        )

    asyncio.run(scenario())


def _mixed_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
    payload = json.loads(request.content)
    prompt = payload["messages"][0]["content"]
    if "Choose the first letter" in prompt:
        return _completion("Reasoning. Answer: A", 10, 2)
    if "Choose B" in prompt:
        return _completion("Final answer: C", 10, 2)
    if "Choose D" in prompt:
        return _completion("I cannot tell.", 10, 2)
    if "JSON object with key ok" in prompt:
        return _completion('{"ok": true}', 8, 4)
    if "exactly two words" in prompt:
        return httpx.Response(400, text="bad request")
    if "Compute 2 + 2" in prompt:
        return _completion("The answer is 4.", 6, 2)
    if "Compute 10 / 2" in prompt:
        return _completion("The answer is 6.", 6, 2)
    return httpx.Response(500, text="unexpected prompt")


def _all_correct_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
    payload = json.loads(request.content)
    prompt = payload["messages"][0]["content"]
    if "Choose the first letter" in prompt:
        return _completion("Answer: A", 1, 1)
    if "JSON object with key ok" in prompt:
        return _completion('{"ok": true}', 1, 1)
    if "Compute 2 + 2" in prompt:
        return _completion("4", 1, 1)
    return httpx.Response(500, text="unexpected prompt")


def _completion(
    text: str,
    prompt_tokens: int,
    completion_tokens: int,
    timings: dict[str, object] | None = None,
) -> httpx.Response:
    body = {
        "choices": [
            {
                "message": {"content": text},
                "finish_reason": "stop",
            },
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
    if timings is not None:
        body["timings"] = timings
    return httpx.Response(
        200,
        json=body,
    )


def _completion_without_usage(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"content": text},
                    "finish_reason": "stop",
                },
            ],
        },
    )


def _raw_completion(
    text: str,
    finish_reason: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"text": text, "finish_reason": finish_reason}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        },
    )

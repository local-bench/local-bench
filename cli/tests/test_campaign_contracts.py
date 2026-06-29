from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from localbench.cli import main
from localbench.orchestrate import OrchestrateConfig, run_localbench

FIXTURE_SUITE = Path(__file__).parent / "fixtures" / "suite_v0"


def test_run_record_reserves_external_endpoint_trust_tier(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: an endpoint-only localbench run.
        output_path = tmp_path / "campaign" / "localbench-run.json"

        # When: the run completes.
        record = await run_localbench(
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

        # Then: the artifact cannot be confused with managed serving verification.
        assert record["trust_tier"] == "external-endpoint"
        assert record["serving_verification_level"] == "external-endpoint"

    asyncio.run(scenario())


def test_status_command_prints_checkpoint_progress(tmp_path: Path, capsys) -> None:
    async def scenario() -> None:
        await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                max_items=1,
                out=tmp_path / "campaign" / "localbench-run.json",
            ),
            transport=httpx.MockTransport(_answer_a_handler),
        )

    asyncio.run(scenario())

    # When: status is requested for the campaign directory.
    code = main(["status", str(tmp_path / "campaign")])

    # Then: status reports advisory progress plus checkpoint completion.
    out = capsys.readouterr().out
    assert code == 0
    assert "state     complete" in out
    assert "progress  1/1" in out
    assert "mmlu_pro" in out


def test_collect_command_writes_redacted_support_bundle(tmp_path: Path, capsys) -> None:
    # Given: a campaign directory containing secret-bearing diagnostics.
    campaign = tmp_path / "campaign"
    (campaign / "logs").mkdir(parents=True)
    (campaign / "monitor").mkdir()
    (campaign / "benchmarks").mkdir()
    (campaign / "campaign.json").write_text(
        json.dumps({"api_key": "sk-secret123456", "endpoint": "http://local/v1"}),
        encoding="utf-8",
    )
    (campaign / "run.status.json").write_text(json.dumps({"state": "failed"}), encoding="utf-8")
    (campaign / "logs" / "run.log").write_text("Authorization: Bearer abc.def.ghi\n", encoding="utf-8")
    (campaign / "monitor" / "monitor.jsonl").write_text(
        json.dumps({"status": "ok", "detail": "no secrets"}) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "support.json"

    # When: collecting a support bundle.
    code = main(["collect", str(campaign), "--out", str(out)])

    # Then: the bundle is redacted and machine-readable.
    stdout = capsys.readouterr().out
    bundle_text = out.read_text(encoding="utf-8")
    bundle = json.loads(bundle_text)
    assert code == 0
    assert "wrote" in stdout
    assert "sk-secret123456" not in bundle_text
    assert "Bearer abc.def.ghi" not in bundle_text
    assert bundle["campaign"]["api_key"] == "***REDACTED***"
    assert bundle["logs"]["run_tail"] == ["Authorization: Bearer ***REDACTED***"]


def _answer_a_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "demo-model"}]})
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "Answer: A"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )

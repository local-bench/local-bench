from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.submissions.bundle import pack_submission_bundle
from localbench.submissions.verify import verify_bundle_offline

from .fixtures import build_submission_fixtures


@pytest.mark.anyio
async def test_tampered_client_aggregate_does_not_change_recomputed_score(tmp_path: Path) -> None:
    # Given: a bundle whose audit-only original run aggregate claims a wrong score.
    fixtures = await build_submission_fixtures(tmp_path)
    tampered = tmp_path / "tampered-aggregate.lbsub.zip"
    run = json.loads(fixtures.run_path.read_text(encoding="utf-8"))
    run["benches"]["mmlu_pro"]["raw_accuracy"] = 0.0
    run["composite"] = 0.0
    fixtures.run_path.write_text(json.dumps(run, sort_keys=True), encoding="utf-8")
    pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=tampered,
        offline=True,
        created_at="2026-06-24T00:00:00Z",
        run_nonce="fixed-nonce",
    )

    # When: verifying the tampered audit data.
    result = verify_bundle_offline(tampered, suite_dir=fixtures.suite_dir)

    # Then: official scores come from raw output re-scoring, not client aggregates.
    assert result["recomputed"]["benches"]["mmlu_pro"]["raw_accuracy"] == 1.0
    assert result["recomputed"]["composite"] == 1.0


@pytest.mark.anyio
async def test_tampered_client_item_correct_does_not_change_recomputed_score(tmp_path: Path) -> None:
    # Given: a bundle whose item audit field lies about correctness.
    fixtures = await build_submission_fixtures(tmp_path)
    tampered = tmp_path / "tampered-item-correct.lbsub.zip"
    run = json.loads(fixtures.run_path.read_text(encoding="utf-8"))
    run["items"][0]["correct"] = False
    fixtures.run_path.write_text(json.dumps(run, sort_keys=True), encoding="utf-8")
    pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=tampered,
        offline=True,
        created_at="2026-06-24T00:00:00Z",
        run_nonce="fixed-nonce",
    )

    # When: verifying the tampered client item score.
    result = verify_bundle_offline(tampered, suite_dir=fixtures.suite_dir)

    # Then: the raw response still re-scores as correct.
    assert result["recomputed"]["items"][0]["correct"] is True
    assert result["recomputed"]["benches"]["mmlu_pro"]["raw_accuracy"] == 1.0


@pytest.mark.anyio
async def test_tampered_raw_output_changes_recomputed_score(tmp_path: Path) -> None:
    # Given: a bundle whose authoritative raw response text is wrong.
    fixtures = await build_submission_fixtures(tmp_path)
    tampered = tmp_path / "tampered-output.lbsub.zip"
    run = json.loads(fixtures.run_path.read_text(encoding="utf-8"))
    run["items"][0]["response_text"] = "Answer: B"
    run["items"][0]["correct"] = True
    fixtures.run_path.write_text(json.dumps(run, sort_keys=True), encoding="utf-8")
    pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=tampered,
        offline=True,
        created_at="2026-06-24T00:00:00Z",
        run_nonce="fixed-nonce",
    )

    # When: verifying the tampered raw output.
    result = verify_bundle_offline(tampered, suite_dir=fixtures.suite_dir)

    # Then: recomputed scoring reflects the raw output, not client scoring.
    assert result["recomputed"]["items"][0]["correct"] is False
    assert result["recomputed"]["benches"]["mmlu_pro"]["raw_accuracy"] == 0.0

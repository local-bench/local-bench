from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.submissions.bundle import pack_submission_bundle
from localbench.submissions.verify import verify_bundle_offline

from .fixtures import build_submission_fixtures


@pytest.mark.anyio
async def test_verify_offline_recomputes_and_marks_community_re_scored(tmp_path: Path) -> None:
    # Given: a valid offline submission bundle.
    fixtures = await build_submission_fixtures(tmp_path)
    bundle = tmp_path / "valid.lbsub.zip"
    out = tmp_path / "verification.json"
    pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=bundle,
        offline=True,
        created_at="2026-06-24T00:00:00Z",
        run_nonce="fixed-nonce",
    )

    # When: verifying offline and writing the verification record.
    result = verify_bundle_offline(bundle, suite_dir=fixtures.suite_dir, out_path=out)

    # Then: the verifier emits only the conservative offline trust label.
    written = json.loads(out.read_text(encoding="utf-8"))
    assert result == written
    assert result["trust_label"] == "community_re_scored"
    assert result["publishable"] is False
    assert result["publishable_reasons"] == ["offline_ticket_not_account_bound"]
    assert result["recomputed"]["benches"]["mmlu_pro"]["raw_accuracy"] == 1.0
    assert result["recomputed"]["composite"] == 1.0
    assert result["divergence"] == {
        "items_compared": 1,
        "items_changed": 0,
        "score_changing_count": 0,
        "classification": "exact",
        "rank_improving_tamper": False,
        "per_item": [
            {
                "id": "mmlu-1",
                "bench": "mmlu_pro",
                "claimed": {"correct": True, "extracted": "A", "failure_kind": None},
                "recomputed": {"correct": True, "extracted": "A", "failure_kind": None},
                "class": "exact",
            },
        ],
    }


@pytest.mark.anyio
async def test_cli_submit_pack_and_verify_offline_round_trip(tmp_path: Path, capsys) -> None:
    # Given: a run file, signing key, and local suite directory.
    from localbench.cli import main

    fixtures = await build_submission_fixtures(tmp_path)
    bundle = tmp_path / "valid.lbsub.zip"
    verification = tmp_path / "verification.json"

    # When: driving M1 through the public CLI surface.
    pack_code = main(
        [
            "submit",
            "pack",
            "--run",
            str(fixtures.run_path),
            "--suite-dir",
            str(fixtures.suite_dir),
            "--model-name",
            "fixture-model",
            "--signing-key",
            str(fixtures.key_path),
            "--out",
            str(bundle),
            "--offline",
            "--created-at",
            "2026-06-24T00:00:00Z",
            "--run-nonce",
            "fixed-nonce",
        ],
    )
    verify_code = main(
        [
            "submit",
            "verify-offline",
            str(bundle),
            "--suite-dir",
            str(fixtures.suite_dir),
            "--out",
            str(verification),
        ],
    )

    # Then: both commands succeed and write the expected files.
    output = capsys.readouterr().out
    assert pack_code == 0
    assert verify_code == 0
    assert "bundle    " in output
    assert "verification" in output
    assert verification.exists()

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from localbench.scoring.axis_status import axis_status_for_benches
from localbench.submissions.attestation import (
    sign_verdict_attestation,
    verify_verdict_attestation,
)
from localbench.submissions.bundle import pack_submission_bundle
from localbench.submissions.canon import canonical_json_bytes, sha256_file
from localbench.submissions.foundation import rescore_bundle
from localbench.submissions.keys import write_private_key
from localbench.submissions.verify import verify_bundle_offline

from .fixtures import build_submission_fixtures


@pytest.mark.anyio
async def test_verify_submission_threads_community_origin_to_projection(tmp_path: Path) -> None:
    from localbench.submissions.status_update import verify_submission

    fixtures = await build_submission_fixtures(tmp_path)
    out = tmp_path / "projection.json"

    status = verify_submission(
        fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        projection_out=out,
        validated_at="2026-07-04T00:00:00Z",
        validator_commit=None,
        origin="community",
    )

    projection = json.loads(out.read_text(encoding="utf-8"))
    assert status["projection_path"] == str(out)
    assert projection["origin"] == "community"
    assert projection["trust_label"] == "community_self_submitted"
    assert projection["verification_level"] == "bundle_rescored"
    assert projection["agentic_provenance"] == "none"


@pytest.mark.anyio
async def test_project_anchor_origin_keeps_anchor_projection_labels(tmp_path: Path) -> None:
    fixtures = await build_submission_fixtures(tmp_path)

    projection = rescore_bundle(
        fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        validated_at="2026-07-04T00:00:00Z",
        origin="project_anchor",
    )

    assert projection["origin"] == "project_anchor"
    assert projection["trust_label"] == "project_anchor"
    assert projection["verification_level"] == "bundle_rescored"
    assert projection["agentic_provenance"] == "none"


def test_verdict_attestation_round_trip_and_tamper_detection(tmp_path: Path) -> None:
    key_path = tmp_path / "attester.pem"
    public_key = write_private_key(key_path, seed=bytes(range(32)))

    record = sign_verdict_attestation(
        bench="appworld_c",
        task_id="task_42",
        run_id="run-fixture",
        verdict={"success": True, "collateral_damage": False},
        attested_at="2026-07-04T00:00:00Z",
        signing_key_path=key_path,
    )

    assert verify_verdict_attestation(record, expected_public_key_hex=public_key) is True

    tampered = json.loads(json.dumps(record))
    tampered["payload"]["verdict"]["success"] = False
    assert verify_verdict_attestation(tampered, expected_public_key_hex=public_key) is False
    assert verify_verdict_attestation(record, expected_public_key_hex="00" * 32) is False


@pytest.mark.anyio
async def test_bundle_attestations_round_trip_and_legacy_absence(tmp_path: Path) -> None:
    from localbench.submissions.archive import unpack_bundle

    fixtures = await build_submission_fixtures(tmp_path)
    public_key = write_private_key(tmp_path / "attester.pem", seed=bytes(range(32)))
    attestation = sign_verdict_attestation(
        bench="appworld_c",
        task_id="task_1",
        run_id="run-fixture",
        verdict={"success": True, "collateral_damage": False},
        attested_at="2026-07-04T00:00:00Z",
        signing_key_path=tmp_path / "attester.pem",
    )
    assert attestation["signature"]["public_key"] == public_key

    with_attestations = tmp_path / "with-attestations.lbsub.zip"
    without_attestations = tmp_path / "without-attestations.lbsub.zip"
    pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=with_attestations,
        offline=True,
        created_at="2026-07-04T00:00:00Z",
        run_nonce="fixed-nonce",
        attestations=[attestation],
    )
    pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=without_attestations,
        offline=True,
        created_at="2026-07-04T00:00:00Z",
        run_nonce="fixed-nonce",
    )

    with zipfile.ZipFile(with_attestations, "r") as archive:
        assert "attestations.jsonl" in archive.namelist()
    with zipfile.ZipFile(without_attestations, "r") as archive:
        assert "attestations.jsonl" not in archive.namelist()
    assert unpack_bundle(with_attestations).attestations == [attestation]
    assert unpack_bundle(without_attestations).attestations == []


@pytest.mark.anyio
async def test_projection_marks_valid_dynamic_attestations_project_attested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import localbench.submissions.attestation as attestation_mod

    fixture = await _dynamic_submission_fixture(tmp_path, (True, False))
    monkeypatch.setattr(attestation_mod, "ATTESTER_PUBLIC_KEY_HEX", fixture.public_key)

    projection = rescore_bundle(
        fixture.bundle,
        suite_dir=fixture.suite_dir,
        validated_at="2026-07-04T00:00:00Z",
        origin="project_anchor",
    )

    assert projection["agentic_provenance"] == "project_attested"
    assert "provenance_notes" not in projection


@pytest.mark.anyio
async def test_projection_degrades_when_a_dynamic_attestation_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import localbench.submissions.attestation as attestation_mod

    fixture = await _dynamic_submission_fixture(tmp_path, (True, False), attest_task_ids=("task_1",))
    monkeypatch.setattr(attestation_mod, "ATTESTER_PUBLIC_KEY_HEX", fixture.public_key)

    projection = rescore_bundle(
        fixture.bundle,
        suite_dir=fixture.suite_dir,
        validated_at="2026-07-04T00:00:00Z",
        origin="project_anchor",
    )

    assert projection["agentic_provenance"] == "self_reported"
    assert projection["provenance_notes"] == ["attestation_missing:appworld_c/task_2"]


@pytest.mark.anyio
async def test_projection_labels_unattested_community_dynamic_items_self_reported(tmp_path: Path) -> None:
    fixture = await _dynamic_submission_fixture(tmp_path, (True,), attest_task_ids=())

    projection = rescore_bundle(
        fixture.bundle,
        suite_dir=fixture.suite_dir,
        validated_at="2026-07-04T00:00:00Z",
        origin="community",
    )

    assert projection["origin"] == "community"
    assert projection["trust_label"] == "community_self_submitted"
    assert projection["agentic_provenance"] == "self_reported"
    assert projection["provenance_notes"] == ["attestation_missing:appworld_c/task_1"]


@pytest.mark.anyio
async def test_projection_grandfathers_allowlisted_dynamic_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import localbench.submissions.projection as projection_mod

    fixture = await _dynamic_submission_fixture(tmp_path, (True,), attest_task_ids=())
    monkeypatch.setattr(
        projection_mod,
        "GRANDFATHERED_ATTESTED_BUNDLE_SHA256S",
        frozenset({sha256_file(fixture.bundle)}),
    )

    projection = rescore_bundle(
        fixture.bundle,
        suite_dir=fixture.suite_dir,
        validated_at="2026-07-04T00:00:00Z",
        origin="project_anchor",
    )

    assert projection["agentic_provenance"] == "project_attested"
    assert "provenance_notes" not in projection


@pytest.mark.anyio
async def test_offline_verify_keeps_trust_label_and_reports_agentic_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import localbench.submissions.attestation as attestation_mod

    fixture = await _dynamic_submission_fixture(tmp_path, (True,))
    monkeypatch.setattr(attestation_mod, "ATTESTER_PUBLIC_KEY_HEX", fixture.public_key)

    result = verify_bundle_offline(fixture.bundle, suite_dir=fixture.suite_dir)

    assert result["trust_label"] == "community_re_scored"
    assert result["agentic_provenance"] == "project_attested"
    assert result["publishable_reasons"] == ["offline_ticket_not_account_bound"]


class DynamicSubmissionFixture:
    def __init__(self, bundle: Path, suite_dir: Path, public_key: str) -> None:
        self.bundle = bundle
        self.suite_dir = suite_dir
        self.public_key = public_key


async def _dynamic_submission_fixture(
    tmp_path: Path,
    successes: tuple[bool, ...],
    *,
    attest_task_ids: tuple[str, ...] | None = None,
) -> DynamicSubmissionFixture:
    fixtures = await build_submission_fixtures(tmp_path)
    _write_dynamic_scorecard(fixtures.suite_dir)
    _append_dynamic_items(fixtures.run_path, successes)
    attester_key = tmp_path / "attester.pem"
    public_key = write_private_key(attester_key, seed=bytes(range(32)))
    selected = {f"task_{index}" for index in range(1, len(successes) + 1)}
    if attest_task_ids is not None:
        selected = set(attest_task_ids)
    attestations = [
        sign_verdict_attestation(
            bench="appworld_c",
            task_id=f"task_{index}",
            run_id="run-fixture",
            verdict={"success": success, "collateral_damage": False},
            attested_at="2026-07-04T00:00:00Z",
            signing_key_path=attester_key,
        )
        for index, success in enumerate(successes, start=1)
        if f"task_{index}" in selected
    ]
    bundle = tmp_path / "dynamic.lbsub.zip"
    pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=bundle,
        offline=True,
        created_at="2026-07-04T00:00:00Z",
        run_nonce="fixed-nonce",
        attestations=attestations,
    )
    return DynamicSubmissionFixture(bundle=bundle, suite_dir=fixtures.suite_dir, public_key=public_key)


def _write_dynamic_scorecard(suite_dir: Path) -> None:
    (suite_dir / "SCORECARD.json").write_text(
        json.dumps(
            {
                "registry": [
                    {"key": "knowledge", "role": "headline", "benches": ["mmlu_pro"], "weight": 0.15},
                    {"key": "agentic", "role": "headline", "benches": ["appworld_c"], "weight": 0.50},
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _append_dynamic_items(run_path: Path, successes: tuple[bool, ...]) -> None:
    run = json.loads(run_path.read_text(encoding="utf-8"))
    items = run["items"]
    assert isinstance(items, list)
    items.extend(_dynamic_item(index, success) for index, success in enumerate(successes, start=1))
    run["benches"]["appworld_c"] = _dynamic_aggregate(successes)
    run["axis_status"] = axis_status_for_benches(run["benches"])
    run_path.write_bytes(canonical_json_bytes(run) + b"\n")


def _dynamic_item(index: int, success: bool) -> dict[str, object]:
    return {
        "bench": "appworld_c",
        "id": f"task_{index}",
        "response_text": None,
        "extracted": None,
        "correct": success,
        "finish_reason": "stop",
        "latency_seconds": 0.0,
        "started_at": "2026-07-04T00:00:00Z",
        "finished_at": "2026-07-04T00:00:00Z",
        "attempts": 1,
        "usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
        "error": None,
    }


def _dynamic_aggregate(successes: tuple[bool, ...]) -> dict[str, object]:
    raw = sum(1 for success in successes if success) / len(successes)
    return {
        "n": len(successes),
        "n_errors": 0,
        "n_extraction_failures": 0,
        "raw_accuracy": raw,
        "chance_corrected": raw,
        "termination_rate": 1.0,
        "conditional_accuracy": raw,
    }

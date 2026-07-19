from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from localbench._suite import item_hashes, read_json_object, render_benches
from localbench._scoring import aggregate
from localbench._types import JsonObject, JsonValue
from localbench.cli import _parser
from localbench.coding_exec.artifacts import code_artifact_for_generation, verified_artifact
from localbench.coding_exec.receipt import attach_signed_verifier_receipt
from localbench.submissions.canon import canonical_json_bytes, write_json_file
from localbench.submissions.foundation import validate_accepted_result_projection
from localbench.submissions.keys import write_private_key
from localbench.submissions.projection import (
    _index_relabel_note,
    _verified_coding_item,
    client_reported_projection,
)
from localbench.submissions.status_update import verify_submission
from localbench.submissions.validate import SubmissionValidationError

from .test_5axis_suite_release import _synthetic_5axis_result_bundle

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RELEASED_SUITE = _REPO_ROOT / "web" / "public" / "suites" / "suite-v1-full-exec-6axis-v1"
_VALIDATED_AT = "2026-07-14T00:00:00Z"
_IMAGE_DIGEST = "bigcodebench/bigcodebench-evaluate@sha256:" + "a" * 64
_HEADLINE_WEIGHTS = {
    "knowledge": 0.225,
    "instruction_following": 0.225,
    "math": 0.075,
    "agentic": 0.25,
    "coding": 0.225,
    "tool_calling": 0.0,
}


def test_full_exec_receipt_projects_verified_coding_as_measured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the receipt/object shapes from the real maintainer artifact at
    # C:/Users/Michael/lb-user-runs/runs/gemma31b-q4km-v2-full/coding-verified.json,
    # rebuilt with synthetic run values and a test-only Ed25519 key.
    fixture = _full_exec_fixture(tmp_path, monkeypatch, with_receipt=True)
    projection_out = tmp_path / "verified-projection.json"

    # When: admission verification receives the matching verifier output.
    status = verify_submission(
        fixture.bundle,
        suite_dir=fixture.suite_dir,
        projection_out=projection_out,
        validated_at=_VALIDATED_AT,
        validator_commit="synthetic-validator-commit",
        origin="project_anchor",
        coding_verified_path=fixture.verified,
    )

    # Then: only the signed verifier verdict becomes ranked coding evidence.
    projection = _object(status["projection"])
    coding = _object(_object(projection["axes"])["coding"])
    validate_accepted_result_projection(projection)
    assert status["accepted"] is True
    assert coding == {"score": 1.0, "n": 141, "ci": None, "status": "measured"}
    assert fixture.verified is not None
    verified = read_json_object(fixture.verified)
    coding_aggregate = aggregate(
        "bigcodebench_hard",
        [
            _verified_coding_item(item)
            for item in verified["items"]
            if isinstance(item, dict) and item.get("bench") == "bigcodebench_hard"
        ],
        0.0,
    )
    assert coding_aggregate["n"] == 141
    assert coding_aggregate["n_unscoreable"] == 7
    assert _object(projection["rescore_modes"])["appworld_c"] == "verdict_carried"
    assert _object(projection["rescore_modes"])["bigcodebench_hard"] == "verdict_carried"
    assert _object(projection["receipt_references"])["coding_receipt_sha256"] is not None
    assert projection["coverage_profile_id"] == "full-exec-6axis-v1"
    assert projection["index_version"] == "index-v4.2"
    assert projection["headline_complete"] is True
    assert projection_out.read_bytes() == canonical_json_bytes(projection) + b"\n"


def test_submitter_projection_carries_locally_graded_coding_and_agentic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _full_exec_fixture(tmp_path, monkeypatch, with_receipt=True)
    assert fixture.verified is not None

    projection = client_reported_projection(
        fixture.verified,
        suite_dir=fixture.suite_dir,
        validated_at=_VALIDATED_AT,
    )

    assert projection["verification_level"] == "client_reported"
    assert projection["headline_complete"] is True
    assert projection["index_version"] == "index-v4.2"
    axes = _object(projection["axes"])
    scores = _object(projection["scores"])
    assert set(axes) == {*_HEADLINE_WEIGHTS, "long_context"}
    assert scores["headline_score"] == _weighted_headline(axes)
    assert scores["partial_composite"] == _weighted_headline(axes)
    assert _object(projection["rescore_modes"])["bigcodebench_hard"] == "verdict_carried"
    assert _object(projection["rescore_modes"])["appworld_c"] == "verdict_carried"
    validate_accepted_result_projection(projection)


def test_legacy_full_exec_bundle_relabels_to_current_index_with_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _full_exec_fixture(tmp_path, monkeypatch, with_receipt=True)
    assert fixture.verified is not None
    legacy = read_json_object(fixture.verified)
    legacy["index_version"] = "index-v3.0"
    write_json_file(fixture.verified, legacy)

    projection = client_reported_projection(
        fixture.verified,
        suite_dir=fixture.suite_dir,
        validated_at=_VALIDATED_AT,
    )

    assert projection["coverage_profile_id"] == "full-exec-6axis-v1"
    assert projection["index_version"] == "index-v4.2"
    assert "index_relabeled_from:index-v3.0" in projection["provenance_notes"]


def test_admission_derives_tool_use_axis_from_legacy_raw_appworld_verdicts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _full_exec_fixture(tmp_path, monkeypatch, with_receipt=False)
    legacy = read_json_object(fixture.bundle)
    legacy["index_version"] = "index-v3.0"
    axes = _object(_object(legacy["axis_status"])["axes"])
    axes["tool_use"] = {
        "axis": "tool_use",
        "status": "not_measured",
        "reason": "not_run",
    }
    agentic_items = [
        {
            "attempts": 1,
            "bench": "appworld_c",
            "correct": index < 6,
            "error": None,
            "extracted": None,
            "finish_reason": None,
            "finished_at": "2026-07-18T19:50:12.949469+00:00",
            "id": f"legacy-agentic-{index:03d}",
            "latency_seconds": 0.0,
            "response_text": None,
            "started_at": "2026-07-18T19:50:12.949469+00:00",
            "usage": {
                "completion_tokens": None,
                "prompt_tokens": None,
                "total_tokens": None,
            },
        }
        for index in range(96)
    ]
    legacy["items"] = [
        item
        for item in legacy["items"]
        if not (isinstance(item, dict) and item.get("bench") == "appworld_c")
    ] + agentic_items
    mmlu_item = next(
        item
        for item in legacy["items"]
        if isinstance(item, dict) and item.get("bench") == "mmlu_pro"
    )
    _object(mmlu_item)["response_text"] = "H"
    _object(legacy["benches"])["appworld_c"] = {
        "n": 96,
        "n_errors": 0,
        "raw_accuracy": 0.0625,
        "chance_corrected": 0.0625,
    }
    write_json_file(fixture.bundle, legacy)

    status = verify_submission(
        fixture.bundle,
        suite_dir=fixture.suite_dir,
        projection_out=tmp_path / "legacy-raw-record.projection.json",
        validated_at=_VALIDATED_AT,
        validator_commit=None,
        origin="project_anchor",
    )

    projection = _object(status["projection"])
    axes = _object(projection["axes"])
    agentic = _object(axes["agentic"])
    scores = _object(projection["scores"])
    assert status["accepted"] is False
    assert status["status"] == "rejected"
    assert "incomplete_run" in status["blocking_reasons"]
    assert agentic == {"score": 0.0625, "n": 96, "ci": None, "status": "measured"}
    assert _object(axes["tool_calling"])["status"] == "measured"
    assert scores["partial_composite"] == _weighted_headline(axes)
    assert scores["measured_headline_weight"] == 0.775
    assert scores["missing_headline_weight"] == 0.225
    assert _object(projection["rescore_modes"])["appworld_c"] == "verdict_carried"
    assert "index_relabeled_from:index-v3.0" in projection["provenance_notes"]


def test_current_profile_rejects_unknown_or_newer_carried_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _full_exec_fixture(tmp_path, monkeypatch, with_receipt=True)
    assert fixture.verified is not None
    mismatched = read_json_object(fixture.verified)
    mismatched["index_version"] = "index-v5.0"
    write_json_file(fixture.verified, mismatched)

    with pytest.raises(ValueError, match="index_version does not match"):
        client_reported_projection(
            fixture.verified,
            suite_dir=fixture.suite_dir,
            validated_at=_VALIDATED_AT,
        )


def test_noncurrent_profile_rejects_an_older_label_mismatch() -> None:
    with pytest.raises(ValueError, match="index_version does not match"):
        _index_relabel_note(
            "index-v4.0",
            coverage_profile_id="static-exec-5axis-v1",
            current_index_version="index-v3.0",
        )


@pytest.mark.parametrize("publishable", [True, False], ids=["valid-sampling", "invalid-sampling"])
def test_full_exec_without_receipt_constructs_schema_valid_status_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    publishable: bool,
) -> None:
    # Given: a full-exec bundle with gen-time coding artifacts but no maintainer receipt.
    fixture = _full_exec_fixture(tmp_path, monkeypatch, with_receipt=False, publishable=publishable)
    stale_bundle = read_json_object(fixture.bundle)
    stale_bundle["headline_complete"] = True
    stale_bundle["receipt_references"] = {"coding_receipt_sha256": "f" * 64}
    write_json_file(fixture.bundle, stale_bundle)

    # When: admission verification constructs either an accept or reject status update.
    status = verify_submission(
        fixture.bundle,
        suite_dir=fixture.suite_dir,
        projection_out=tmp_path / f"{publishable}.projection.json",
        validated_at=_VALIDATED_AT,
        validator_commit=None,
        origin="project_anchor",
    )

    # Then: generated-only coding remains incomplete regardless of the sampler state.
    projection = _object(status["projection"])
    coding = _object(_object(projection["axes"])["coding"])
    validate_accepted_result_projection(projection)
    assert status["accepted"] is False
    assert status["status"] == "rejected"
    assert "incomplete_run" in status["blocking_reasons"]
    assert coding == {"score": None, "n": 0, "ci": None, "status": "not_measured"}
    assert projection["headline_complete"] is False
    assert _object(projection["receipt_references"])["coding_receipt_sha256"] is None
    assert "generated_unverified" not in json.dumps(projection, sort_keys=True)


def test_admission_without_coding_execution_cannot_claim_measured_coding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the axis-status shape from cli/tests/test_axis_measurement_status.py,
    # but no BigCodeBench item that could support its generated measured claim.
    fixture = _full_exec_fixture(
        tmp_path,
        monkeypatch,
        with_receipt=False,
        with_coding_evidence=False,
    )

    # When: the bundle is assembled for an admission decision.
    status = verify_submission(
        fixture.bundle,
        suite_dir=fixture.suite_dir,
        projection_out=tmp_path / "no-coding.projection.json",
        validated_at=_VALIDATED_AT,
        validator_commit=None,
        origin="project_anchor",
    )

    # Then: absence of execution evidence wins over the bundle's measured assertion.
    projection = _object(status["projection"])
    coding = _object(_object(projection["axes"])["coding"])
    validate_accepted_result_projection(projection)
    assert coding == {"score": None, "n": 0, "ci": None, "status": "not_measured"}


@pytest.mark.parametrize("failure", ["bad_signature", "wrong_run"])
def test_invalid_coding_receipt_raises_typed_error_without_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    # Given: a real-shape, test-signed receipt that is either tampered or bound to other bytes.
    fixture = _full_exec_fixture(
        tmp_path,
        monkeypatch,
        with_receipt=True,
        receipt_source_bytes=b"synthetic-wrong-run-bytes" if failure == "wrong_run" else None,
    )
    if failure == "bad_signature":
        verified = read_json_object(fixture.verified)
        receipt = _object(verified["coding_verifier_receipt"])
        signature = _object(receipt["signature"])
        signature["signature"] = "0" * 128
        receipt["signature"] = signature
        verified["coding_verifier_receipt"] = receipt
        write_json_file(fixture.verified, verified)
    projection_out = tmp_path / "must-not-exist.json"

    # When / Then: receipt failure is explicit and nothing can be posted or persisted.
    with pytest.raises(SubmissionValidationError, match="signature|bound to the submitted run") as error_info:
        verify_submission(
            fixture.bundle,
            suite_dir=fixture.suite_dir,
            projection_out=projection_out,
            validated_at=_VALIDATED_AT,
            validator_commit=None,
            origin="project_anchor",
            coding_verified_path=fixture.verified,
        )
    assert type(error_info.value).__name__ == "CodingVerificationError"
    assert not projection_out.exists()


def test_admin_verify_parser_accepts_explicit_coding_verified_path() -> None:
    # Given / When: the operator supplies the verifier output to admin-verify.
    args = _parser().parse_args(
        [
            "submit",
            "admin-verify",
            "--site",
            "https://local-bench.ai",
            "--submission-id",
            "sub_synthetic",
            "--bundle",
            "bundle.zip",
            "--suite-dir",
            "suite",
            "--projection-out",
            "projection.json",
            "--coding-verified",
            "coding-verified.json",
        ],
    )

    # Then: the option remains opt-in and reaches the command namespace as a Path.
    assert args.coding_verified == Path("coding-verified.json")


class _FullExecFixture:
    def __init__(self, *, bundle: Path, suite_dir: Path, verified: Path | None) -> None:
        self.bundle = bundle
        self.suite_dir = suite_dir
        self.verified = verified


def _full_exec_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    with_receipt: bool,
    publishable: bool = True,
    with_coding_evidence: bool = True,
    receipt_source_bytes: bytes | None = None,
) -> _FullExecFixture:
    suite_dir = tmp_path / "suite"
    shutil.copytree(_RELEASED_SUITE, suite_dir)
    # Shape copied from cli/tests/submissions/test_projection_dynamic_benches.py; this
    # local registry makes appworld_c a verdict-carried headline bench in the fixture.
    (suite_dir / "SCORECARD.json").write_text(
        json.dumps(
            {
                "registry": [
                    {"key": "tool_use", "role": "headline", "benches": ["appworld_c"], "weight": 0.2},
                    {"key": "coding", "role": "headline", "benches": ["bigcodebench_hard"], "weight": 0.24},
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    release = read_json_object(suite_dir / "suite_release_manifest.json")
    bundle = _synthetic_5axis_result_bundle(release)
    _object(bundle["benches"]).pop("lcb", None)
    suite = read_json_object(suite_dir / "suite.json")
    item_files = [
        str(_object(value["itemsets"])["standard"]["file"])
        for value in _object(suite["benches"]).values()
    ]
    suite_manifest = _object(_object(bundle["manifest"])["suite"])
    suite_manifest.update(
        {
            "suite_version": suite["version"],
            "tier": "standard",
            "item_set_hashes": item_hashes(suite_dir, item_files),
        },
    )
    _object(bundle["manifest"])["suite"] = suite_manifest
    if not publishable:
        _object(_object(bundle["manifest"])["sampling"])["top_k"] = 0

    rendered = render_benches("bigcodebench_hard", "standard", None, suite_dir, suite, [])
    coding_bench = rendered[0]
    static_items: list[JsonObject] = []
    for bench_name in ("mmlu_pro", "ifbench", "tc_json_v1", "olymmath_hard", "amo"):
        static_bench = render_benches(bench_name, "standard", 1, suite_dir, suite, [])[0]
        static_items.append(
            {
                "id": str(static_bench.benchmark_items[0]["id"]),
                "bench": bench_name,
                "response_text": "",
                "finish_reason": "stop",
                "latency_seconds": 0.0,
                "started_at": "2026-07-14T00:00:00Z",
                "finished_at": "2026-07-14T00:00:00Z",
                "attempts": 1,
                "usage": {"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1},
                "error": None,
                "correct": False,
                "extracted": None,
            },
        )
    coding_items: list[JsonObject] = []
    for source_item, benchmark_item in zip(
        coding_bench.source_items,
        coding_bench.benchmark_items,
        strict=True,
    ):
        coding_item: JsonObject = {
            "id": str(benchmark_item["id"]),
            "bench": "bigcodebench_hard",
            "response_text": "def task_func(*args, **kwargs):\n    return None",
            "reasoning_text": None,
            "finish_reason": "stop",
            "latency_seconds": 0.25,
            "started_at": "2026-07-14T00:00:00Z",
            "finished_at": "2026-07-14T00:00:01Z",
            "attempts": 1,
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            "error": None,
            "correct": False,
            "extracted": "def task_func(*args, **kwargs):\n    return None",
        }
        coding_item["code_artifact"] = code_artifact_for_generation(
            source_item,
            benchmark_item,
            coding_item,
        )
        coding_items.append(coding_item)
    # Item shape copied from cli/tests/submissions/test_projection_dynamic_benches.py.
    agentic_item: JsonObject = {
        "id": "synthetic-agentic-1",
        "bench": "appworld_c",
        "correct": True,
        "response_text": None,
        "extracted": None,
        "finish_reason": None,
        "latency_seconds": 0.0,
        "started_at": "2026-07-14T00:00:00Z",
        "finished_at": "2026-07-14T00:00:00Z",
        "attempts": 1,
        "usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
        "error": None,
    }
    bundle["items"] = static_items + (coding_items if with_coding_evidence else []) + [agentic_item]
    benches: JsonObject = {
        **_object(bundle["benches"]),
        "appworld_c": {"n": 1, "n_errors": 0, "raw_accuracy": 1.0, "chance_corrected": 1.0},
        "olymmath_hard": {"n": 1, "n_errors": 0, "raw_accuracy": 0.0, "chance_corrected": 0.0},
        "amo": {"n": 1, "n_errors": 0, "raw_accuracy": 0.0, "chance_corrected": 0.0},
    }
    if with_coding_evidence:
        benches["bigcodebench_hard"] = {
            "n": len(coding_items),
            "n_errors": 0,
            "raw_accuracy": 0.0,
            "chance_corrected": 0.0,
        }
    bundle["benches"] = benches
    coding_axis: JsonObject = (
        {"axis": "coding", "status": "measured", "reason": "ok"}
        if with_receipt
        else
        {
            "axis": "coding",
            "status": "generated_unverified",
            "reason": "verdict_pending",
            "detail": "BigCodeBench-Hard artifacts generated; verifier verdict pending",
        }
        if with_coding_evidence
        else {"axis": "coding", "status": "measured", "reason": "ok"}
    )
    bundle["axis_status"] = {
        "schema_version": "localbench.axis-status.v1",
        "axes": {
            "knowledge": {"axis": "knowledge", "status": "measured", "reason": "ok"},
            "instruction_following": {
                "axis": "instruction_following",
                "status": "measured",
                "reason": "ok",
            },
            "math": {"axis": "math", "status": "measured", "reason": "ok"},
            "agentic": {"axis": "agentic", "status": "measured", "reason": "ok"},
            "tool_calling": {"axis": "tool_calling", "status": "measured", "reason": "ok"},
            "coding": coding_axis,
        },
    }
    bundle_path = tmp_path / "full-exec-result-bundle.json"
    write_json_file(bundle_path, bundle)
    if not with_receipt:
        return _FullExecFixture(bundle=bundle_path, suite_dir=suite_dir, verified=None)

    verified = copy.deepcopy(bundle)
    for index, raw_item in enumerate(verified["items"]):
        verified_item = _object(raw_item)
        if verified_item.get("bench") != "bigcodebench_hard":
            continue
        verified_item["correct"] = True
        verified_item["code_artifact"] = verified_artifact(
            _object(verified_item["code_artifact"]),
            verdict={
                "passed": True,
                "timeout": False,
                "oom": False,
                "runtime_ms": 1,
                "stdout_tail": "",
                "stderr_tail": "",
            },
            image_digest=_IMAGE_DIGEST,
        )
        verified["items"][index] = verified_item
    key_path = tmp_path / "test-verifier.pem"
    public_key = write_private_key(key_path, seed=bytes(range(32)))
    attach_signed_verifier_receipt(
        verified,
        source_bytes=receipt_source_bytes or (json.dumps(bundle, indent=2) + "\n").encode("utf-8"),
        suite_dir=suite_dir,
        image_digest=_IMAGE_DIGEST,
        signing_key=key_path,
    )
    verified_path = tmp_path / "coding-verified.json"
    verified_path.write_text(
        json.dumps(verified, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    import localbench.submissions.status_update as status_update

    monkeypatch.setattr(status_update, "_CODING_VERIFIER_PUBLIC_KEY", public_key)
    return _FullExecFixture(bundle=bundle_path, suite_dir=suite_dir, verified=verified_path)


def _object(value: JsonValue) -> JsonObject:
    assert isinstance(value, dict)
    return value


def _weighted_headline(axes: JsonObject) -> float:
    return round(
        sum(
            weight * float(_object(axes[axis])["score"] or 0.0)
            for axis, weight in _HEADLINE_WEIGHTS.items()
        ),
        4,
    )

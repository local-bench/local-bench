from __future__ import annotations

import copy
from pathlib import Path

import pytest

from localbench._suite import read_json_object
from localbench.coding_exec.receipt import CodingVerificationError
from localbench.submissions.bundle_input import load_result_bundle_input
from localbench.submissions.canon import write_json_file
from localbench.submissions.status_update import verify_submission
from localbench.submissions.validate import SubmissionValidationError

from .test_admin_verify_coding_receipt import (
    _VALIDATED_AT,
    _full_exec_fixture,
    _object,
)


def test_admission_rejects_receipt_from_different_model_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a valid signed receipt document whose verified run names another model artifact.
    fixture = _full_exec_fixture(tmp_path, monkeypatch, with_receipt=True)
    assert fixture.verified is not None
    verified = read_json_object(fixture.verified)
    _object(_object(verified["manifest"])["model"])["file_sha256"] = "f" * 64
    write_json_file(fixture.verified, verified)

    # When / Then: admission rejects the cross-run identity before projecting a score.
    with pytest.raises(CodingVerificationError, match="model identity"):
        _verify(fixture.bundle, fixture.suite_dir, fixture.verified, tmp_path)


def test_admission_rejects_subset_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a signed receipt document with one favorable coding item removed.
    fixture = _full_exec_fixture(tmp_path, monkeypatch, with_receipt=True)
    assert fixture.verified is not None
    verified = read_json_object(fixture.verified)
    verified["items"] = [
        item
        for item in verified["items"]
        if not (isinstance(item, dict) and item.get("id") == "bcbh-148")
    ]
    write_json_file(fixture.verified, verified)

    # When / Then: exact trusted-suite coverage is mandatory.
    with pytest.raises(CodingVerificationError, match="missing coding item"):
        _verify(fixture.bundle, fixture.suite_dir, fixture.verified, tmp_path)


def test_admission_rejects_duplicate_receipt_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a receipt document containing a duplicated passing coding row.
    fixture = _full_exec_fixture(tmp_path, monkeypatch, with_receipt=True)
    assert fixture.verified is not None
    verified = read_json_object(fixture.verified)
    verified["items"] = [*verified["items"], copy.deepcopy(verified["items"][0])]
    write_json_file(fixture.verified, verified)

    # When / Then: duplicate IDs are a typed verification failure.
    with pytest.raises(CodingVerificationError, match="duplicate coding item"):
        _verify(fixture.bundle, fixture.suite_dir, fixture.verified, tmp_path)


def test_admission_rejects_extra_receipt_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a receipt document containing a coding row outside the trusted suite.
    fixture = _full_exec_fixture(tmp_path, monkeypatch, with_receipt=True)
    assert fixture.verified is not None
    verified = read_json_object(fixture.verified)
    extra = copy.deepcopy(verified["items"][0])
    _object(extra)["id"] = "bcbh-untrusted-extra"
    verified["items"] = [*verified["items"], extra]
    write_json_file(fixture.verified, verified)

    # When / Then: exact trusted-suite coverage rejects untrusted extra IDs.
    with pytest.raises(CodingVerificationError, match="extra coding item"):
        _verify(fixture.bundle, fixture.suite_dir, fixture.verified, tmp_path)


def test_admission_rejects_generation_content_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the submitted generation differs from the generation the verifier executed.
    fixture = _full_exec_fixture(tmp_path, monkeypatch, with_receipt=True)
    assert fixture.verified is not None
    bundle = read_json_object(fixture.bundle)
    _object(bundle["items"][0])["response_text"] = "def task_func():\n    return 'different'"
    write_json_file(fixture.bundle, bundle)

    # When / Then: semantic generation identity is mandatory per coding ID.
    with pytest.raises(CodingVerificationError, match="generation"):
        _verify(fixture.bundle, fixture.suite_dir, fixture.verified, tmp_path)


def test_admission_rejects_bool_for_integer_sampling_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: Python-coercing values that compare equal (`True == 1`) but are distinct JSON types.
    fixture = _full_exec_fixture(tmp_path, monkeypatch, with_receipt=True)
    assert fixture.verified is not None
    bundle = read_json_object(fixture.bundle)
    _object(_object(bundle["manifest"])["sampling"])["top_k"] = True
    write_json_file(fixture.bundle, bundle)

    # When / Then: admission compares canonical JSON values with exact recursive types.
    with pytest.raises(CodingVerificationError, match="manifest identity"):
        _verify(fixture.bundle, fixture.suite_dir, fixture.verified, tmp_path)


def test_admission_rejects_duplicate_key_in_verified_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a verified document with a duplicate top-level key that ordinary json.loads accepts.
    fixture = _full_exec_fixture(tmp_path, monkeypatch, with_receipt=True)
    assert fixture.verified is not None
    raw = fixture.verified.read_text(encoding="utf-8")
    fixture.verified.write_text('{"schema_version":"shadow",' + raw[1:], encoding="utf-8")

    # When / Then: the admission JSON boundary rejects duplicate keys.
    with pytest.raises(CodingVerificationError, match="duplicate JSON key"):
        _verify(fixture.bundle, fixture.suite_dir, fixture.verified, tmp_path)


@pytest.mark.parametrize(
    "source",
    [
        b'{"schema_version":"first","schema_version":"second"}',
        b'{"schema_version":NaN}',
    ],
    ids=["duplicate-key", "non-standard-number"],
)
def test_result_bundle_loader_rejects_non_standard_json(tmp_path: Path, source: bytes) -> None:
    # Given: JSON outside the strict interoperable document model.
    bundle = tmp_path / "bundle.json"
    bundle.write_bytes(source)

    # When / Then: parsing fails at the submission boundary.
    with pytest.raises(SubmissionValidationError, match="duplicate JSON key|non-standard JSON"):
        load_result_bundle_input(bundle)


def _verify(bundle: Path, suite_dir: Path, verified: Path, tmp_path: Path) -> None:
    verify_submission(
        bundle,
        suite_dir=suite_dir,
        projection_out=tmp_path / "must-not-exist.json",
        validated_at=_VALIDATED_AT,
        validator_commit=None,
        origin="project_anchor",
        coding_verified_path=verified,
    )

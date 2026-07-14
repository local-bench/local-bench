from __future__ import annotations

from pathlib import Path

import pytest

from localbench._suite import read_json_object
from localbench.coding_exec.receipt import CodingVerificationError
from localbench.landing import LandingError, _assert_generations_untouched, verify_coding_run
from localbench.submissions.bundle_input import load_result_bundle_input

from submissions.test_admin_verify_coding_receipt import _full_exec_fixture, _object


def test_landing_rejects_admission_reconstructed_source_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a receipt bound to reconstructed pretty JSON, not the exact submitted file bytes.
    fixture = _full_exec_fixture(tmp_path, monkeypatch, with_receipt=True)
    assert fixture.verified is not None
    loaded = load_result_bundle_input(fixture.bundle)
    verified = read_json_object(fixture.verified)
    receipt = _object(verified["coding_verifier_receipt"])
    public_key = str(_object(receipt["signature"])["public_key"])

    # When / Then: maintainer landing accepts only the exact original-file SHA-256.
    with pytest.raises(CodingVerificationError, match="original run bytes"):
        verify_coding_run(
            loaded.record,
            loaded.source_bytes,
            fixture.verified,
            suite_dir=fixture.suite_dir,
            verifier_public_key=public_key,
        )


def test_landing_generation_guard_distinguishes_bool_from_integer() -> None:
    # Given: two documents that Python's coercing equality considers equal.
    original = {"manifest": {"sampling": {"top_k": 1}}, "items": []}
    verified = {"manifest": {"sampling": {"top_k": True}}, "items": []}

    # When / Then: landing's document comparison preserves exact recursive JSON types.
    with pytest.raises(LandingError, match="non-coding top-level"):
        _assert_generations_untouched(original, verified)

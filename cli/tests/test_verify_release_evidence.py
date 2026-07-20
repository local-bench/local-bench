from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from localbench._types import JsonObject
from localbench.submissions.canon import canonical_json_hash
from release_evidence_test_support import (
    ReleaseFixture,
    build_evidence,
    make_release,
    run_verifier,
    write_evidence,
)


@pytest.fixture
def release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ReleaseFixture:
    return make_release(tmp_path, monkeypatch)


def _assert_rejected(
    tmp_path: Path,
    release: ReleaseFixture,
    evidence: JsonObject,
    mode: str,
    reason: str,
) -> None:
    completed = run_verifier(
        release,
        (write_evidence(tmp_path, evidence),),
        "--mode",
        mode,
    )
    assert completed.returncode == 1
    assert completed.stdout.splitlines()[-1] == f"FAIL: {reason}"


def test_verifier_accepts_complete_differential_evidence(
    tmp_path: Path,
    release: ReleaseFixture,
) -> None:
    evidence = build_evidence(release)
    evidence_path = write_evidence(tmp_path, evidence)

    completed = run_verifier(release, (evidence_path,), "--expect-self-test", "0")

    assert completed.returncode == 0, completed.stderr
    assert f"evidence_sha256={canonical_json_hash(evidence)}" in completed.stdout
    assert completed.stdout.splitlines()[-1].startswith("PASS ")


def test_verifier_rejects_flipped_differential_verdict(
    tmp_path: Path,
    release: ReleaseFixture,
) -> None:
    evidence = build_evidence(release)
    evidence["verdict"] = "fail"
    _assert_rejected(
        tmp_path,
        release,
        evidence,
        "differential",
        "differential verdict must be pass",
    )


def test_verifier_rejects_wrong_contract_sha(
    tmp_path: Path,
    release: ReleaseFixture,
) -> None:
    evidence = build_evidence(release)
    evidence["contract_payload_sha256"] = "0" * 64
    _assert_rejected(
        tmp_path,
        release,
        evidence,
        "differential",
        "contract payload sha256 mismatch",
    )


def test_verifier_rejects_wrong_rootfs_sha(
    tmp_path: Path,
    release: ReleaseFixture,
) -> None:
    evidence = build_evidence(release)
    evidence["rootfs_sha256"] = "0" * 64
    _assert_rejected(
        tmp_path,
        release,
        evidence,
        "differential",
        "rootfs sha256 mismatch",
    )


def test_verifier_rejects_nonempty_differential_diffs(
    tmp_path: Path,
    release: ReleaseFixture,
) -> None:
    evidence = build_evidence(release)
    evidence["diffs"] = [{"field": "worker_identity"}]
    _assert_rejected(
        tmp_path,
        release,
        evidence,
        "differential",
        "differential diffs must be empty",
    )


def test_verifier_rejects_self_test_that_passed(
    tmp_path: Path,
    release: ReleaseFixture,
) -> None:
    evidence = build_evidence(release, mode="self-test")
    _assert_rejected(
        tmp_path,
        release,
        evidence,
        "self-test",
        "self-test verdict must be fail",
    )


def test_verifier_accepts_designed_self_test_drift(
    tmp_path: Path,
    release: ReleaseFixture,
) -> None:
    evidence = deepcopy(build_evidence(release, mode="self-test"))
    evidence["verdict"] = "fail"
    evidence["diffs"] = [
        {
            "field": "startup_failure",
            "detail": "wsl worker error: agentic execution contract drift",
        }
    ]

    completed = run_verifier(
        release,
        (write_evidence(tmp_path, evidence),),
        "--expect-self-test",
        "1",
    )

    assert completed.returncode == 0, completed.stdout
    assert completed.stdout.splitlines()[-1].startswith("PASS ")

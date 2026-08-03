from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Never

import pytest

from localbench.checkset.models import ChecksetBuildError, JsonObject
from localbench.check_cli import main as check_main
from localbench.cli import main
from localbench.checkset.build import _freeze_reviewed_draft
from localbench.checkset.command import build_command
from localbench.submissions.canon import canonical_json_bytes


def _complete_draft() -> JsonObject:
    return {
        "draft": True,
        "edition": "check-set-v1",
        "status": "complete-draft",
    }


def _canonical_sha256(document: JsonObject) -> str:
    return hashlib.sha256(canonical_json_bytes(document) + b"\n").hexdigest()


def test_freeze_records_review_when_fresh_draft_matches_reviewed_sha() -> None:
    # Given a complete draft whose canonical bytes carry the reviewed digest.
    draft = _complete_draft()
    reviewed_sha256 = _canonical_sha256(draft)
    # When the reviewed draft is frozen.
    frozen = _freeze_reviewed_draft(draft, reviewed_sha256)

    # Then only freeze metadata changes and the caller's draft remains untouched.
    assert draft == _complete_draft()
    assert frozen == {
        "draft": False,
        "edition": "check-set-v1",
        "review": {
            "draft_sha256": reviewed_sha256,
            "reviewed_by": "orchestrator",
            "reviewed_local": "2026-08-03",
        },
        "status": "frozen",
        "supersedes": {
            "previous_frozen_sha256": "96896021d6befb40187d8cef53a98beadde4cd2348c719ee0c492176e59cf0a7",
            "reason": "pre-validation construction defect: deepest needle window exceeded LCE context under real tokenizers",
            "corrected_local": "2026-08-03",
        },
    }


def test_freeze_rejects_fresh_draft_that_differs_from_reviewed_sha() -> None:
    # Given a reviewed digest for different canonical draft content.
    # When freeze is attempted, then the unreviewed draft is rejected with both digests.
    with pytest.raises(ChecksetBuildError, match=r"refusing to freeze unreviewed check-set-v1 draft"):
        _freeze_reviewed_draft(_complete_draft(), "0" * 64)


@pytest.mark.parametrize("reviewed_sha256", (None, "f" * 63, "g" * 64))
def test_freeze_rejects_missing_or_malformed_reviewed_sha(reviewed_sha256: str | None) -> None:
    with pytest.raises(ChecksetBuildError, match="reviewed draft sha256"):
        _freeze_reviewed_draft(_complete_draft(), reviewed_sha256)


def test_both_internal_cli_surfaces_require_and_thread_reviewed_draft_sha(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: list[tuple[bool, str | None]] = []

    def fake_build_command(
        _repo_root: Path,
        _output: Path,
        *,
        offline_upstream: bool,
        freeze: bool = False,
        reviewed_draft_sha: str | None = None,
    ) -> tuple[int, str]:
        _ = offline_upstream
        captured.append((freeze, reviewed_draft_sha))
        return 0, "accepted"

    monkeypatch.setattr("localbench.cli.build_checkset_command", fake_build_command)
    monkeypatch.setattr("localbench.checkset.command.build_command", fake_build_command)
    args = (
        "checkset",
        "build",
        "--repo-root",
        str(tmp_path),
        "--output",
        str(tmp_path / "manifest.json"),
        "--freeze",
        "--reviewed-draft-sha",
        "a" * 64,
    )

    assert main(args) == 0
    assert check_main(args) == 0
    assert captured == [(True, "a" * 64), (True, "a" * 64)]


def test_freeze_boundary_rejects_missing_reviewed_sha_before_building(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def unexpected_build(_repo_root: Path) -> Never:
        raise AssertionError("freeze input validation must precede manifest construction")

    monkeypatch.setattr("localbench.checkset.command.build_local_modules", unexpected_build)

    exit_code, message = build_command(
        tmp_path,
        tmp_path / "manifest.json",
        offline_upstream=True,
        freeze=True,
    )

    assert exit_code == 2
    assert message == "reviewed draft sha256 must be a 64-character hexadecimal value"


def test_checkset_build_freeze_refuses_incomplete_offline_build(tmp_path: Path) -> None:
    # Given the internal builder cannot fetch either pinned upstream dependency.
    output = tmp_path / "manifest.json"
    repo_root = Path(__file__).resolve().parents[2]

    # When freeze mode is requested through the real CLI.
    exit_code = main(
        (
            "checkset",
            "build",
            "--repo-root",
            str(repo_root),
            "--output",
            str(output),
            "--offline-upstream",
            "--freeze",
            "--reviewed-draft-sha",
            "0" * 64,
        )
    )

    # Then it refuses without writing an incomplete scaffold over the target.
    assert exit_code == 2
    assert not output.exists()

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import localbench.checkset.build as build_module
from localbench.checkset.models import ChecksetBuildError, JsonObject
from localbench.cli import main
from localbench.submissions.canon import canonical_json_bytes


def _complete_draft() -> JsonObject:
    return {
        "draft": True,
        "edition": "check-set-v1",
        "status": "complete-draft",
    }


def _canonical_sha256(document: JsonObject) -> str:
    return hashlib.sha256(canonical_json_bytes(document) + b"\n").hexdigest()


def test_freeze_records_review_when_fresh_draft_matches_reviewed_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a complete draft whose canonical bytes carry the reviewed digest.
    draft = _complete_draft()
    reviewed_sha256 = _canonical_sha256(draft)
    monkeypatch.setattr(build_module, "REVIEWED_DRAFT_SHA256", reviewed_sha256)

    # When the reviewed draft is frozen.
    frozen = build_module._freeze_reviewed_draft(draft)

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
    }


def test_freeze_rejects_fresh_draft_that_differs_from_reviewed_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a reviewed digest for different canonical draft content.
    monkeypatch.setattr(build_module, "REVIEWED_DRAFT_SHA256", "0" * 64)

    # When freeze is attempted, then the unreviewed draft is rejected with both digests.
    with pytest.raises(ChecksetBuildError, match=r"refusing to freeze unreviewed check-set-v1 draft"):
        build_module._freeze_reviewed_draft(_complete_draft())


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
        )
    )

    # Then it refuses without writing an incomplete scaffold over the target.
    assert exit_code == 2
    assert not output.exists()

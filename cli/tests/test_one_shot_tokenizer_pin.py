from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.exit_codes import EXIT_COMPLETE
from localbench.one_shot.download import DownloadError
from localbench.one_shot.runner import run_one_shot_bench
from one_shot_fixtures import REV_A, TOKENIZER_REV_A, TOKENIZER_REV_B
from one_shot_runner_fakes import _CatalogLoader, _args, _deps


def test_one_shot_cross_repo_tokenizer_resolves_own_revision_and_locks_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deps = _deps(tmp_path)

    code = run_one_shot_bench(
        _args(tmp_path, one_shot_submit=False),
        cli_version="0.2.5",
        deps=deps,
        is_tty=False,
        input_fn=lambda: "",
    )

    assert code == EXIT_COMPLETE
    assert deps.hf_client.revision_calls == ["owner/base-model"]
    assert deps.hf_client.snapshot_calls == [
        {
            "repo_id": "owner/base-model",
            "revision": TOKENIZER_REV_A,
            "destination": tmp_path / "tokenizer" / "owner__base-model" / TOKENIZER_REV_A,
        },
    ]
    lock = json.loads((tmp_path / "plan.lock.json").read_text(encoding="utf-8"))
    assert lock["tokenizer_repo"] == "owner/base-model"
    assert lock["tokenizer_revision"] == TOKENIZER_REV_A
    assert f"tokenizer  owner/base-model@{TOKENIZER_REV_A[:12]} (pinned at run start)" in capsys.readouterr().out


def test_one_shot_same_repo_tokenizer_inherits_artifact_revision_without_resolving(
    tmp_path: Path,
) -> None:
    deps = _deps(tmp_path)
    deps.catalog_loader = _CatalogLoader(tokenizer_repo="owner/model-gguf")

    code = run_one_shot_bench(
        _args(tmp_path, one_shot_submit=False),
        cli_version="0.2.5",
        deps=deps,
        is_tty=False,
        input_fn=lambda: "",
    )

    assert code == EXIT_COMPLETE
    assert deps.hf_client.revision_calls == []
    assert deps.hf_client.snapshot_calls == [
        {
            "repo_id": "owner/model-gguf",
            "revision": REV_A,
            "destination": tmp_path / "tokenizer" / "owner__model-gguf" / REV_A,
        },
    ]


def test_one_shot_resume_reuses_locked_tokenizer_revision_without_resolving_again(
    tmp_path: Path,
) -> None:
    deps = _deps(tmp_path)
    first_code = run_one_shot_bench(
        _args(tmp_path, one_shot_submit=False),
        cli_version="0.2.5",
        deps=deps,
        is_tty=False,
        input_fn=lambda: "",
    )
    deps.hf_client.tokenizer_revision = TOKENIZER_REV_B

    resumed_code = run_one_shot_bench(
        _args(tmp_path, resume=tmp_path),
        cli_version="0.2.5",
        deps=deps,
        is_tty=False,
        input_fn=lambda: "",
    )

    assert first_code == EXIT_COMPLETE
    assert resumed_code == EXIT_COMPLETE
    assert deps.hf_client.revision_calls == ["owner/base-model"]
    assert deps.hf_client.snapshot_calls[-1] == {
        "repo_id": "owner/base-model",
        "revision": TOKENIZER_REV_A,
        "destination": tmp_path / "tokenizer" / "owner__base-model" / TOKENIZER_REV_A,
    }


def test_one_shot_reports_tokenizer_resolution_failures_with_repo_and_fix(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deps = _deps(tmp_path)
    deps.hf_client.tokenizer_revision_error = DownloadError(
        "could not resolve tokenizer repo owner/base-model; log in to Hugging Face or rerun online",
    )

    code = run_one_shot_bench(
        _args(tmp_path, one_shot_submit=False),
        cli_version="0.2.5",
        deps=deps,
        is_tty=False,
        input_fn=lambda: "",
    )

    assert code == 2
    stderr = capsys.readouterr().err
    assert "owner/base-model" in stderr
    assert "log in to Hugging Face or rerun online" in stderr

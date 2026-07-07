from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import localbench.cli as cli_mod


class FakeTokenizer:
    chat_template = "{% for message in messages %}{{ message.content }}{% endfor %}"


@pytest.mark.parametrize(
    "argv",
    (
        ["cache-tokenizer", "--hf-model-id", "unsloth/gemma-4-12b-it"],
        ["cache-tokenizer", "unsloth/gemma-4-12b-it"],
    ),
)
def test_cache_tokenizer_downloads_allowed_files_and_verifies_offline(
    argv: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: Hugging Face download succeeds and offline tokenizer loading sees the cached repo.
    calls: list[tuple[str, tuple[str, ...]]] = []
    snapshot_path = tmp_path / "models--unsloth--gemma-4-12b-it" / "snapshots" / "abc123"

    def fake_snapshot_download(repo_id: str, allow_patterns: list[str]) -> str:
        calls.append((repo_id, tuple(allow_patterns)))
        return str(snapshot_path)

    loaded_repos: list[str] = []

    def fake_load(repo: str) -> FakeTokenizer:
        loaded_repos.append(repo)
        return FakeTokenizer()

    monkeypatch.setattr(cli_mod, "_hf_snapshot_download", fake_snapshot_download, raising=False)
    monkeypatch.setattr(cli_mod, "load_hf_chat_template_tokenizer", fake_load, raising=False)

    # When: the cache-tokenizer command runs.
    code = cli_mod.main(argv)

    # Then: only offline-template files are downloaded and the cached tokenizer is verified.
    output = capsys.readouterr().out
    expected_sha = hashlib.sha256(FakeTokenizer.chat_template.encode("utf-8")).hexdigest()
    assert code == 0
    assert calls == [
        (
            "unsloth/gemma-4-12b-it",
            ("*.json", "*.model", "*.jinja", "*.txt", "*.tiktoken"),
        ),
    ]
    assert loaded_repos == ["unsloth/gemma-4-12b-it"]
    assert "cached    repo unsloth/gemma-4-12b-it" in output
    assert "revision  abc123" in output
    assert f"template  sha256:{expected_sha}" in output


def test_cache_tokenizer_reports_hf_auth_failures_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: Hugging Face rejects the repo because the license/auth gate is not satisfied.
    class GatedRepoError(RuntimeError):
        pass

    def fake_snapshot_download(repo_id: str, allow_patterns: list[str]) -> str:
        raise GatedRepoError("401 gated")

    monkeypatch.setattr(cli_mod, "_hf_snapshot_download", fake_snapshot_download, raising=False)

    # When: the cache command runs.
    code = cli_mod.main(["cache-tokenizer", "--hf-model-id", "owner/gated-model"])

    # Then: the CLI gives the user-facing remediation without a traceback.
    stderr = capsys.readouterr().err
    assert code == 2
    assert "accept the license on huggingface.co" in stderr
    assert "hf auth login" in stderr
    assert "Traceback" not in stderr


def test_cache_tokenizer_reports_missing_hf_extra_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: the huggingface_hub dependency is unavailable.
    def fake_snapshot_download(repo_id: str, allow_patterns: list[str]) -> str:
        raise ImportError("No module named huggingface_hub")

    monkeypatch.setattr(cli_mod, "_hf_snapshot_download", fake_snapshot_download, raising=False)

    # When: the cache command runs.
    code = cli_mod.main(["cache-tokenizer", "owner/model"])

    # Then: it matches the localbench[hf] remediation style without a traceback.
    stderr = capsys.readouterr().err
    assert code == 2
    assert "install localbench[hf]" in stderr
    assert "Hugging Face tokenizer caching" in stderr
    assert "Traceback" not in stderr

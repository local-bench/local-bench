from __future__ import annotations

import sys
from types import ModuleType
from typing import ClassVar

import pytest

from localbench.prompt_rendering import PromptRenderingError, load_hf_chat_template_tokenizer

PINNED_REVISION = "c1899de28999fdb6c871a5a1c94338267a79f43f"


class _FakeTokenizer:
    pass


class _RecordingAutoTokenizer:
    calls: ClassVar[list[tuple[str, bool, str | None]]] = []

    @classmethod
    def from_pretrained(
        cls,
        repo_id: str,
        *,
        local_files_only: bool,
        revision: str | None,
    ) -> _FakeTokenizer:
        cls.calls.append((repo_id, local_files_only, revision))
        return _FakeTokenizer()


class _FailingAutoTokenizer:
    @classmethod
    def from_pretrained(
        cls,
        repo_id: str,
        *,
        local_files_only: bool,
        revision: str | None,
    ) -> _FakeTokenizer:
        raise OSError(f"offline miss: {repo_id}@{revision}")


def test_load_hf_chat_template_tokenizer_passes_explicit_revision_to_transformers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _RecordingAutoTokenizer.calls = []
    _install_transformers(monkeypatch, _RecordingAutoTokenizer)

    tokenizer = load_hf_chat_template_tokenizer(
        "Qwen/Qwen3-0.6B",
        revision=PINNED_REVISION,
    )

    assert isinstance(tokenizer, _FakeTokenizer)
    assert _RecordingAutoTokenizer.calls == [
        ("Qwen/Qwen3-0.6B", True, PINNED_REVISION),
    ]


def test_load_hf_chat_template_tokenizer_keeps_manual_revision_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _RecordingAutoTokenizer.calls = []
    _install_transformers(monkeypatch, _RecordingAutoTokenizer)

    tokenizer = load_hf_chat_template_tokenizer("Qwen/Qwen3-0.6B")

    assert isinstance(tokenizer, _FakeTokenizer)
    assert _RecordingAutoTokenizer.calls == [
        ("Qwen/Qwen3-0.6B", True, None),
    ]


def test_load_hf_chat_template_tokenizer_error_names_requested_repo_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_transformers(monkeypatch, _FailingAutoTokenizer)

    with pytest.raises(PromptRenderingError) as exc_info:
        load_hf_chat_template_tokenizer(
            "Qwen/Qwen3-0.6B",
            revision=PINNED_REVISION,
        )

    message = str(exc_info.value)
    assert f"Qwen/Qwen3-0.6B@{PINNED_REVISION}" in message
    assert "pinned revision was requested" in message


def _install_transformers(
    monkeypatch: pytest.MonkeyPatch,
    auto_tokenizer: type[_RecordingAutoTokenizer] | type[_FailingAutoTokenizer],
) -> None:
    module = ModuleType("transformers")
    setattr(module, "AutoTokenizer", auto_tokenizer)
    monkeypatch.setitem(sys.modules, "transformers", module)

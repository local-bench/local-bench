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


def test_cache_miss_message_names_both_remedies(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the offline loader misses (stubbed - never import real transformers here).
    import localbench.prompt_rendering as pr

    _install_transformers(monkeypatch, _RecordingAutoTokenizer)

    def raise_oserror(auto_tokenizer, request):
        raise OSError("not in cache")

    monkeypatch.setattr(pr, "_load_offline_tokenizer", raise_oserror)

    # When / Then: the curated miss message offers BOTH remedies.
    with pytest.raises(pr.TokenizerCacheMissError) as excinfo:
        pr.load_hf_chat_template_tokenizer("owner/model")
    message = str(excinfo.value)
    assert "hf download owner/model" in message
    assert "--gguf-repo-only" in message


def test_unexpected_introspection_failure_becomes_prompt_rendering_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a community repo's tokenizer config makes transformers raise an
    # arbitrary exception type (oracle BLOCKER 2).
    import localbench.prompt_rendering as pr

    _install_transformers(monkeypatch, _RecordingAutoTokenizer)

    def raise_typeerror(auto_tokenizer, request):
        raise TypeError("unexpected keyword argument 'sp_model_kwargs'")

    monkeypatch.setattr(pr, "_load_offline_tokenizer", raise_typeerror)

    # When / Then: it surfaces as the typed, catchable error - not a raw TypeError.
    with pytest.raises(pr.PromptRenderingError) as excinfo:
        pr.load_hf_chat_template_tokenizer("owner/model")
    assert "TypeError" in str(excinfo.value)
    assert not isinstance(excinfo.value, pr.TokenizerCacheMissError)

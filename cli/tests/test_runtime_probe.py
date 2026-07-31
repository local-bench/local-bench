from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final

import pytest

from localbench._types import JsonObject
from localbench.bounded_final_profiles import (
    BoundedFinalProfileRequest,
    BoundedFinalProfileRuntime,
    resolve_bounded_final_profile,
)
from localbench.execution_contract import execution_contract_resume_identity
from localbench.gguf_template import LLAMA_BUILTIN_CHATML_NONTHINKING
from localbench.runtime_probe import (
    RUNTIME_PROBE_MISMATCH,
    RuntimeProbeMismatchError,
    verify_llama_cpp_runtime_profile,
)

_MODEL_SHA: Final = "a" * 64
_BUILD: Final[JsonObject] = {
    "executable_sha256": "b" * 64,
    "version_stdout": "b10076-305ba519a",
}


@dataclass(frozen=True, slots=True)
class _StubBehavior:
    no_tools_prompt: str
    tools_prompt: str
    reasoning_content: str | None
    renderer_prompt: str | None = None
    completion_max_tokens: list[int] | None = None


def _runtime(
    template: str | None,
    *,
    profile: str = "auto",
    base_url: str = "http://llama.test",
) -> BoundedFinalProfileRuntime:
    metadata: JsonObject = {}
    if template is not None:
        metadata = {
            "tokenizer.chat_template": template,
            "tokenizer.ggml.eos_token_id": 0,
            "tokenizer.ggml.tokens": ["<|im_end|>"],
        }
    return resolve_bounded_final_profile(
        BoundedFinalProfileRequest(
            profile=profile,
            hf_model_id=None,
            model_file_sha256=_MODEL_SHA,
            gguf_metadata=metadata,
            llama_apply_template_base_url=base_url,
            llama_api_key="secret",
            gguf_repo_only=True,
        )
    )


@contextmanager
def _stub_server(behavior: _StubBehavior) -> Iterator[str]:
    no_tools_requests = 0

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/props":
                self.send_error(404)
                return
            self._reply({"build_info": "b10076", "chat_template": "stub"})

        def do_POST(self) -> None:
            nonlocal no_tools_requests
            size = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(size))
            if self.path == "/apply-template":
                if isinstance(body, dict) and body.get("tools"):
                    prompt = behavior.tools_prompt
                else:
                    no_tools_requests += 1
                    prompt = (
                        behavior.renderer_prompt
                        if no_tools_requests > 1 and behavior.renderer_prompt is not None
                        else behavior.no_tools_prompt
                    )
                self._reply({"prompt": prompt})
                return
            if self.path == "/v1/chat/completions":
                if behavior.completion_max_tokens is not None:
                    behavior.completion_max_tokens.append(body["max_tokens"])
                self._reply(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": "",
                                    "reasoning_content": behavior.reasoning_content,
                                }
                            }
                        ]
                    }
                )
                return
            self.send_error(404)

        def log_message(self, format: str, *args: str) -> None:
            return

        def _reply(self, payload: JsonObject) -> None:
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.anyio
async def test_thinking_candidate_with_confirming_probe_proceeds(tmp_path: Path) -> None:
    # Given: static GGUF evidence proposes thinking and both runtime variants agree.
    behavior = _StubBehavior(
        no_tools_prompt="<|im_start|>assistant\n<think>\n",
        tools_prompt="<|im_start|>assistant\n<think>\n",
        reasoning_content="bounded reasoning",
    )

    # When: the launched llama.cpp server is probed with the resolved kwargs.
    with _stub_server(behavior) as base_url:
        runtime = _runtime(
            "{% if enable_thinking %}<think>{% endif %}<|im_end|>",
            base_url=base_url,
        )
        provisional_identity = execution_contract_resume_identity(runtime.contract)
        confirmed = await verify_llama_cpp_runtime_profile(
            base_url=base_url,
            model_id="fixture-model",
            api_key="secret",
            runtime=runtime,
            llama_build=_BUILD,
            run_dir=tmp_path,
        )

    # Then: behavioral evidence becomes immutable contract and disk evidence.
    assert confirmed.contract.runtime_probe is not None
    assert confirmed.contract.runtime_probe["passed"] is True
    assert confirmed.contract.effective_template_sha256 is not None
    assert execution_contract_resume_identity(confirmed.contract) != provisional_identity
    assert json.loads((tmp_path / "runtime-probe.json").read_text())["passed"] is True


@pytest.mark.anyio
async def test_behavioral_probe_uses_its_small_local_generation_bound(
    tmp_path: Path,
) -> None:
    # Given: a deep-budget profile whose execution caps are much larger than a probe needs.
    captured: list[int] = []
    behavior = _StubBehavior(
        no_tools_prompt="<|im_start|>assistant\n<think>\n",
        tools_prompt="<|im_start|>assistant\n<think>\n",
        reasoning_content="bounded reasoning",
        completion_max_tokens=captured,
    )

    # When: its template/reasoning behavior is probed.
    with _stub_server(behavior) as base_url:
        runtime = _runtime(
            "{% if enable_thinking %}<think>{% endif %}<|im_end|>",
            profile="generic_think_tags_32768_v1",
            base_url=base_url,
        )
        await verify_llama_cpp_runtime_profile(
            base_url=base_url,
            model_id="fixture-model",
            api_key="secret",
            runtime=runtime,
            llama_build=_BUILD,
            run_dir=tmp_path,
        )

    # Then: request capture proves no 32k/49k/64k contract capacity leaked into generation.
    assert captured == [16]


@pytest.mark.anyio
async def test_thinking_candidate_without_active_opener_aborts(tmp_path: Path) -> None:
    # Given: static evidence proposes thinking but the runtime closes it immediately.
    behavior = _StubBehavior(
        no_tools_prompt="<think>\n</think>\n",
        tools_prompt="<think>\n</think>\n",
        reasoning_content=None,
    )

    # When: runtime authority contradicts the provisional candidate.
    with _stub_server(behavior) as base_url:
        runtime = _runtime(
            "{% if enable_thinking %}<think>{% endif %}<|im_end|>",
            base_url=base_url,
        )
        with pytest.raises(RuntimeProbeMismatchError, match=RUNTIME_PROBE_MISMATCH):
            await verify_llama_cpp_runtime_profile(
                base_url=base_url,
                model_id="fixture-model",
                api_key="secret",
                runtime=runtime,
                llama_build=_BUILD,
                run_dir=tmp_path,
            )

    # Then: the failed evidence is retained for diagnosis.
    assert json.loads((tmp_path / "runtime-probe.json").read_text())["passed"] is False


@pytest.mark.anyio
async def test_nonthinking_candidate_showing_thinking_aborts(tmp_path: Path) -> None:
    # Given: static evidence proposes non-thinking but llama.cpp opens reasoning.
    runtime = _runtime("<|im_start|>assistant\n<|im_end|>")
    behavior = _StubBehavior(
        no_tools_prompt="<|im_start|>assistant\n<think>\n",
        tools_prompt="<|im_start|>assistant\n<think>\n",
        reasoning_content="unexpected reasoning",
    )

    # When/Then: runtime authority rejects the contradictory execution contract.
    with _stub_server(behavior) as base_url:
        with pytest.raises(RuntimeProbeMismatchError, match=RUNTIME_PROBE_MISMATCH):
            await verify_llama_cpp_runtime_profile(
                base_url=base_url,
                model_id="fixture-model",
                api_key="secret",
                runtime=runtime,
                llama_build=_BUILD,
                run_dir=tmp_path,
            )


@pytest.mark.anyio
async def test_absent_template_builtin_chatml_nonthinking_proceeds(tmp_path: Path) -> None:
    # Given: no GGUF template exists and llama.cpp applies non-thinking ChatML.
    runtime = _runtime(None)
    behavior = _StubBehavior(
        no_tools_prompt="<|im_start|>assistant\n",
        tools_prompt="<|im_start|>assistant\n",
        reasoning_content=None,
    )

    # When: runtime behavior confirms the only publishable fallback.
    with _stub_server(behavior) as base_url:
        confirmed = await verify_llama_cpp_runtime_profile(
            base_url=base_url,
            model_id="fixture-model",
            api_key="secret",
            runtime=runtime,
            llama_build=_BUILD,
            run_dir=tmp_path,
        )

    # Then: the frozen fallback reason and answer-only mode are preserved.
    assert confirmed.contract.selection_reason == LLAMA_BUILTIN_CHATML_NONTHINKING
    assert confirmed.contract.reasoning_mode == "disabled"
    assert confirmed.contract.runtime_probe is not None
    assert confirmed.contract.runtime_probe["passed"] is True


@pytest.mark.anyio
async def test_tools_variant_semantic_flip_aborts(tmp_path: Path) -> None:
    # Given: the default variant thinks while the tools variant suppresses thinking.
    behavior = _StubBehavior(
        no_tools_prompt="<|im_start|>assistant\n<think>\n",
        tools_prompt="<|im_start|>assistant\n",
        reasoning_content="bounded reasoning",
    )

    # When/Then: named-template drift fails closed before any suite item runs.
    with _stub_server(behavior) as base_url:
        runtime = _runtime(
            "{% if enable_thinking %}<think>{% endif %}<|im_end|>",
            base_url=base_url,
        )
        with pytest.raises(RuntimeProbeMismatchError, match=RUNTIME_PROBE_MISMATCH):
            await verify_llama_cpp_runtime_profile(
                base_url=base_url,
                model_id="fixture-model",
                api_key="secret",
                runtime=runtime,
                llama_build=_BUILD,
                run_dir=tmp_path,
            )


@pytest.mark.anyio
async def test_explicit_answer_only_profile_is_behaviorally_verified(tmp_path: Path) -> None:
    # Given: the user explicitly selects answer-only and runtime suppresses reasoning.
    runtime = _runtime(
        "{% if enable_thinking %}<think>{% endif %}<|im_end|>",
        profile="answer_only_v1",
    )
    behavior = _StubBehavior(
        no_tools_prompt="<think>\n</think>\n",
        tools_prompt="<think>\n</think>\n",
        reasoning_content="",
    )

    # When: the explicit profile receives the same authoritative runtime probe.
    with _stub_server(behavior) as base_url:
        confirmed = await verify_llama_cpp_runtime_profile(
            base_url=base_url,
            model_id="fixture-model",
            api_key="secret",
            runtime=runtime,
            llama_build=_BUILD,
            run_dir=tmp_path,
        )

    # Then: explicit answer-only remains disabled and is marked passed.
    assert confirmed.contract.reasoning_mode == "disabled"
    assert confirmed.contract.runtime_probe is not None
    assert confirmed.contract.runtime_probe["passed"] is True


@pytest.mark.anyio
async def test_probe_separates_renderer_evidence_and_keeps_prompts_local(
    tmp_path: Path,
) -> None:
    # Given: the server probe and scoring renderer return identical prompt bytes.
    prompt = "<|im_start|>assistant\n<think>\n"
    behavior = _StubBehavior(
        no_tools_prompt=prompt,
        tools_prompt=prompt,
        reasoning_content="bounded reasoning",
    )

    # When: the generic GGUF runtime is probed through both rendering paths.
    with _stub_server(behavior) as base_url:
        runtime = _runtime(
            "{% if enable_thinking %}<think>{% endif %}<|im_end|>",
            base_url=base_url,
        )
        confirmed = await verify_llama_cpp_runtime_profile(
            base_url=base_url,
            model_id="fixture-model",
            api_key="secret",
            runtime=runtime,
            llama_build=_BUILD,
            run_dir=tmp_path,
        )

    # Then: local evidence retains prompts while contract evidence contains hashes only.
    local_evidence = json.loads((tmp_path / "runtime-probe.json").read_text())
    comparison = local_evidence["renderer_comparison"]
    assert comparison == {
        "raw_template_sha256": runtime.contract.raw_template_sha256,
        "client_prompt_sha256": (
            "77e86abe5a0e443dec1a1c5764625e3ea156e97126b4328dd26c1c6f384365b5"
        ),
        "client_prompt_length": 30,
        "server_prompt_sha256": (
            "77e86abe5a0e443dec1a1c5764625e3ea156e97126b4328dd26c1c6f384365b5"
        ),
        "server_prompt_length": 30,
        "request_shape_sha256": (
            "4b75605e1e92fbd0728674a1ee88b857fe0619e242694a45bbc375e1c35cacc5"
        ),
        "context_sha256": runtime.contract.prompt_renderer_context_sha256,
        "first_mismatch_offset": None,
        "diagnostic_subcode": None,
    }
    assert local_evidence["prompts"]["client"] == prompt
    assert local_evidence["prompts"]["server"] == prompt
    assert confirmed.contract.runtime_probe is not None
    assert "prompts" not in confirmed.contract.runtime_probe
    assert confirmed.contract.runtime_probe["renderer_comparison"] == comparison


@pytest.mark.anyio
async def test_probe_reports_renderer_byte_mismatch_with_first_offset(
    tmp_path: Path,
) -> None:
    # Given: the second server render differs from the authoritative probe response.
    behavior = _StubBehavior(
        no_tools_prompt="<|im_start|>assistant\n<think>\n",
        tools_prompt="<|im_start|>assistant\n<think>\n",
        renderer_prompt="<|im_start|>assistant\n<think>X\n",
        reasoning_content="bounded reasoning",
    )

    # When: the corruption sentinel compares exact UTF-8 prompt bytes.
    with _stub_server(behavior) as base_url:
        runtime = _runtime(
            "{% if enable_thinking %}<think>{% endif %}<|im_end|>",
            base_url=base_url,
        )
        with pytest.raises(
            RuntimeProbeMismatchError,
            match="renderer_byte_mismatch",
        ):
            await verify_llama_cpp_runtime_profile(
                base_url=base_url,
                model_id="fixture-model",
                api_key="secret",
                runtime=runtime,
                llama_build=_BUILD,
                run_dir=tmp_path,
            )

    # Then: the local failure artifact names the subcode and first differing byte.
    evidence = json.loads((tmp_path / "runtime-probe.json").read_text())
    assert evidence["passed"] is False
    assert evidence["renderer_comparison"]["diagnostic_subcode"] == (
        "renderer_byte_mismatch"
    )
    assert evidence["renderer_comparison"]["first_mismatch_offset"] == 29

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final

import pytest

from localbench import cli as cli_mod
from localbench._types import JsonObject, JsonValue
from localbench.execution_contract import structured_execution_profile
from localbench.serving import runner as serving_runner
from localbench.serving.llama_cpp import BuildIdentity
from localbench.serving.model_artifact import ModelArtifact
from localbench.serving.readiness import ReadinessEvidence
from localbench.serving.teardown import TeardownEvidence
from localbench.submissions.canon import sha256_file

_IM_END: Final = "<|im_end|>"
_QWOPUS_TEMPLATE_TAIL: Final = """\
{%- if message.role == "user" %}
    {{- '<|im_start|>' + message.role + '\n' + content + '<|im_end|>\n' }}
{%- elif message.role == "assistant" %}
    {%- if '</think>' in content %}
        {%- set reasoning_content = content.split('</think>')[0].split('<think>')[-1] %}
    {%- endif %}
    {{- '<|im_start|>' + message.role + '\n' + content + '<|im_end|>\n' }}
{%- endif %}
{%- if add_generation_prompt %}
    {{- '<|im_start|>assistant\n' }}
    {%- if enable_thinking is defined and enable_thinking is false %}
        {{- '<think>\n\n</think>\n\n' }}
    {%- else %}
        {{- '<think>\n' }}
    {%- endif %}
{%- endif %}
"""
_EXPECTED_INITIAL_PROMPT: Final = (
    "<|im_start|>user\n"
    "Choose the first letter.\n\n"
    "A. Alpha\n"
    "B. Beta\n"
    "C. Gamma\n"
    "D. Delta\n\n"
    "Answer with one letter.\n"
    "<|im_end|>\n"
    "<|im_start|>assistant\n"
    "<think>\n"
)


class _FakeProcess:
    pid = 1234
    returncode = 0


class _FakeLaunch:
    process = _FakeProcess()
    job = object()
    job_handle = 1

    def close_log(self) -> None:
        return


class _LlamaStub:
    def __init__(self) -> None:
        self.apply_template_requests: list[JsonObject] = []
        self.completion_requests: list[JsonObject] = []
        self.authorizations: list[str | None] = []
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> _LlamaStub:
        state = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/props":
                    self._send({})
                    return
                if self.path == "/v1/models":
                    self._send({"data": [{"id": "qwopus"}]})
                    return
                self.send_error(404)

            def do_POST(self) -> None:
                payload = self._payload()
                state.authorizations.append(self.headers.get("Authorization"))
                if self.path == "/apply-template":
                    state.apply_template_requests.append(payload)
                    self._send({"prompt": _render_prompt(payload)})
                    return
                if self.path == "/v1/chat/completions":
                    self._send(
                        {
                            "choices": [
                                {
                                    "message": {
                                        "content": "ok",
                                        "reasoning_content": "probe",
                                    },
                                    "finish_reason": "stop",
                                }
                            ],
                            "usage": {
                                "prompt_tokens": 1,
                                "completion_tokens": 1,
                                "total_tokens": 2,
                            },
                        }
                    )
                    return
                if self.path == "/v1/completions":
                    state.completion_requests.append(payload)
                    first_pass = len(state.completion_requests) == 1
                    self._send(
                        {
                            "choices": [
                                {
                                    "text": (
                                        "reasoning tokens"
                                        if first_pass
                                        else f"A{_IM_END}"
                                    ),
                                    "finish_reason": (
                                        "length" if first_pass else "stop"
                                    ),
                                }
                            ],
                            "usage": {
                                "prompt_tokens": 10,
                                "completion_tokens": 8_192 if first_pass else 2,
                                "total_tokens": 8_202 if first_pass else 12,
                            },
                        }
                    )
                    return
                self.send_error(404)

            def log_message(self, _format: str, *_args: object) -> None:
                return

            def _payload(self) -> JsonObject:
                length = int(self.headers.get("Content-Length", "0"))
                value = json.loads(self.rfile.read(length))
                assert isinstance(value, dict)
                return value

            def _send(self, payload: JsonObject) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        assert self.server is not None
        self.server.shutdown()
        self.server.server_close()
        assert self.thread is not None
        self.thread.join(timeout=5)

    @property
    def port(self) -> int:
        assert self.server is not None
        return self.server.server_port


def test_public_cli_generic_gguf_runs_server_renderer_and_forced_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suite_dir = _write_suite(tmp_path / "suite")
    model = tmp_path / "qwopus.Q5_K_M.gguf"
    model.write_bytes(b"hermetic gguf artifact")
    server_bin = tmp_path / "llama-server.exe"
    server_bin.write_bytes(b"hermetic server")
    metadata_path = tmp_path / "gguf_metadata.json"
    metadata = {
        "tokenizer.chat_template": _QWOPUS_TEMPLATE_TAIL,
        "tokenizer.ggml.eos_token_id": 0,
        "tokenizer.ggml.tokens": [_IM_END],
    }
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    artifact = ModelArtifact(
        model_file=model,
        file_sha256=sha256_file(model),
        file_size_bytes=model.stat().st_size,
        gguf_metadata_sha256=sha256_file(metadata_path),
        tokenizer_digest="2" * 64,
        chat_template_digest=hashlib.sha256(
            _QWOPUS_TEMPLATE_TAIL.encode("utf-8"),
        ).hexdigest(),
        gguf_metadata_path=metadata_path,
        model_family="qwen3",
        quant_label="Q5_K_M",
    )
    captured_profiles = []
    real_run_localbench = serving_runner.run_localbench

    async def capture_profile(config, **kwargs):
        profile = config.resolved_bounded_profile
        assert profile is not None
        assert profile.prompt_renderer is not None
        captured_profiles.append(profile)
        return await real_run_localbench(config, **kwargs)

    with _LlamaStub() as stub:
        monkeypatch.setattr(cli_mod, "_preflight_execution_contract", lambda: None)
        monkeypatch.setattr(
            serving_runner,
            "resolve_artifact",
            lambda _options, _root: artifact,
        )
        monkeypatch.setattr(serving_runner, "allocate_port", lambda: stub.port)
        monkeypatch.setattr(
            serving_runner,
            "collect_build_identity",
            lambda _binary: _build_identity(),
        )
        monkeypatch.setattr(
            serving_runner,
            "validate_strict_argv_supported",
            lambda _argv, _help: None,
        )
        monkeypatch.setattr(
            serving_runner,
            "launch_llama_cpp",
            lambda _argv, *, cwd, log_path: _FakeLaunch(),
        )
        monkeypatch.setattr(
            serving_runner,
            "verify_llama_cpp_readiness",
            _fake_readiness,
        )
        monkeypatch.setattr(
            serving_runner,
            "teardown_owned_server",
            lambda **_kwargs: TeardownEvidence(
                owned_process_tree=["1234"],
                terminated=True,
                exit_code=0,
                gpu_pids_after=[],
                teardown_uncertain=False,
            ),
        )
        monkeypatch.setattr(serving_runner, "run_localbench", capture_profile)

        out_dir = tmp_path / "run"
        exit_code = cli_mod.main(
            [
                "bench",
                "--runtime",
                "llama.cpp",
                "--model-file",
                str(model),
                "--model-id",
                "qwopus",
                "--server-bin",
                str(server_bin),
                "--ctx",
                "32768",
                "--determinism",
                "strict",
                "--tier",
                "quick",
                "--bench",
                "mmlu_pro",
                "--lane",
                "bounded-final-v1",
                "--profile",
                "auto",
                "--gguf-repo-only",
                "--seed",
                "1234",
                "--max-items",
                "1",
                "--suite-dir",
                str(suite_dir),
                "--out",
                str(out_dir),
                "--no-submit",
                "--accept-suite-terms",
            ]
        )

    assert exit_code == 0
    assert len(captured_profiles) == 1
    contract = captured_profiles[0].contract
    assert contract.prompt_renderer_engine == "llama.cpp/apply-template"
    assert len(stub.completion_requests) == 2
    first, continuation = stub.completion_requests
    assert first["prompt"] == _EXPECTED_INITIAL_PROMPT
    assert first["max_tokens"] == 8_192
    assert continuation["prompt"] == (
        _EXPECTED_INITIAL_PROMPT + "reasoning tokens\n</think>\n\n"
    )
    assert all(value is not None and value.startswith("Bearer ") for value in stub.authorizations)

    record = json.loads(
        (out_dir / "localbench-run.json").read_text(encoding="utf-8"),
    )
    campaign = json.loads((out_dir / "campaign.json").read_text(encoding="utf-8"))
    campaign_contract = campaign["execution_profile"]
    manifest_profile = record["manifest"]["execution_profile"]
    public_projection = structured_execution_profile(manifest_profile)
    assert campaign_contract["id"] == manifest_profile["id"]
    assert campaign_contract["selection_policy_id"] == manifest_profile["selection_policy_id"]
    assert campaign_contract["selection_reason"] == manifest_profile["selection_reason"]
    assert campaign_contract["chat_template_kwargs"] == manifest_profile["chat_template_kwargs"]
    assert campaign_contract["answer_stops"] == manifest_profile["answer_stops"]
    assert public_projection == manifest_profile
    assert record["manifest"]["suite"]["caps"]["thinking_budget"] == 8_192
    assert record["serving"]["resolved_runtime"]["reasoning"]["budget"] == 8_192


def _render_prompt(payload: Mapping[str, JsonValue]) -> str:
    messages = payload["messages"]
    assert isinstance(messages, list)
    assert payload["chat_template_kwargs"] == {"enable_thinking": True}
    assert payload["add_generation_prompt"] is True
    parts: list[str] = []
    for message in messages:
        assert isinstance(message, dict)
        parts.append(
            f"<|im_start|>{message['role']}\n"
            f"{message['content']}<|im_end|>\n",
        )
    return "".join(parts) + "<|im_start|>assistant\n<think>\n"


def _write_suite(path: Path) -> Path:
    path.mkdir(parents=True)
    item = {
        "question_id": 1,
        "question": "Choose the first letter.",
        "options": ["Alpha", "Beta", "Gamma", "Delta"],
        "answer": "A",
    }
    item_bytes = (json.dumps(item, separators=(",", ":")) + "\n").encode("utf-8")
    (path / "mmlu_pro_quick.jsonl").write_bytes(item_bytes)
    (path / "suite.json").write_text(
        json.dumps(
            {
                "version": "suite-renderer-blackbox-v1",
                "benches": {
                    "mmlu_pro": {
                        "chance_correction_baseline": 0.25,
                        "decoding": {"max_tokens": 16_384, "temperature": 0},
                        "itemsets": {
                            "quick": {
                                "file": "mmlu_pro_quick.jsonl",
                                "item_count": 1,
                                "sha256": hashlib.sha256(item_bytes).hexdigest(),
                            }
                        },
                        "lane_caps": {},
                        "template_text": (
                            "{question}\n\n{options}\n\n"
                            "Answer with one letter.\n"
                        ),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (path / "itemsets.lock.json").write_text(
        json.dumps(
            {
                "files": {
                    "mmlu_pro_quick.jsonl": {
                        "sha256": hashlib.sha256(item_bytes).hexdigest(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _build_identity() -> BuildIdentity:
    return BuildIdentity(
        executable_sha256="e" * 64,
        dll_or_so_hashes={"ggml-cuda.dll": "d" * 64},
        version_stdout="llama.cpp b10076 305ba519a",
        source_repo="ggml-org/llama.cpp",
        source_commit="305ba519a",
        source_tag="b10076",
        build_flags="cuda",
        help_text_sha256="h" * 64,
        help_text="",
        list_devices_stdout="CUDA0",
        cuda_version="12.4",
    )


async def _fake_readiness(**_kwargs: object) -> ReadinessEvidence:
    return ReadinessEvidence(
        health_200_at="2026-07-30T00:00:00Z",
        models_response_sha256="m" * 64,
        props_response_sha256="p" * 64,
        reported_model="qwopus",
        smoke_chat_sha256="s" * 64,
        tokenize_sha256="t" * 64,
        apply_template_sha256="a" * 64,
        total_slots=1,
        model_path="qwopus.Q5_K_M.gguf",
        chat_template=_QWOPUS_TEMPLATE_TAIL,
        build_info="llama.cpp b10076 305ba519a",
    )

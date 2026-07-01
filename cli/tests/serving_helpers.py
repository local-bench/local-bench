from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from localbench._types import JsonObject
from localbench.serving.fingerprint import server_fingerprint
from localbench.serving.model_artifact import resolve_model_file_artifact
from localbench.serving.provenance import ServingEvidence
from localbench.serving.teardown import TeardownController


def flag_value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def answer_a_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "demo-model"}]})
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "Answer: A"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )


def minimal_gguf() -> bytes:
    payload = bytearray()
    payload.extend(b"GGUF")
    payload.extend((3).to_bytes(4, "little"))
    payload.extend((0).to_bytes(8, "little"))
    entries = {
        "general.architecture": "gemma",
        "general.name": "Gemma 12B",
        "tokenizer.ggml.model": "gpt2",
        "tokenizer.chat_template": "{{messages}}",
    }
    payload.extend(len(entries).to_bytes(8, "little"))
    for key, value in entries.items():
        encoded_key = key.encode("utf-8")
        encoded_value = value.encode("utf-8")
        payload.extend(len(encoded_key).to_bytes(8, "little"))
        payload.extend(encoded_key)
        payload.extend((8).to_bytes(4, "little"))
        payload.extend(len(encoded_value).to_bytes(8, "little"))
        payload.extend(encoded_value)
    return bytes(payload)


def serving_evidence(tmp_path: Path, *, teardown_terminated: bool) -> ServingEvidence:
    artifact = resolve_model_file_artifact(write_minimal_model(tmp_path), run_dir=tmp_path / "run")
    argv = ["llama-server.exe", "--parallel", "1", "--ctx-size", "32768"]
    fingerprint = server_fingerprint(
        model_file_sha256=artifact.file_sha256,
        executable_sha256="e" * 64,
        argv=argv,
        env_allowlist={"CUDA_VISIBLE_DEVICES": "0"},
        ctx=32768,
        kv_cache_quant="k=f16,v=f16",
        parallel_slots=1,
        flash_attention="on",
        chat_template_digest=artifact.chat_template_digest or "",
    )
    return ServingEvidence(
        runtime="llama.cpp",
        argv=argv,
        cwd=str(tmp_path),
        env_allowlist={"CUDA_VISIBLE_DEVICES": "0"},
        host="127.0.0.1",
        port=49152,
        api_key_sha256="a" * 64,
        artifact=artifact,
        executable_sha256="e" * 64,
        dll_or_so_hashes={"ggml-cuda.dll": "d" * 64},
        version_stdout="llama.cpp b9852 fd1a05791",
        source_repo="ggml-org/llama.cpp",
        source_commit="fd1a05791",
        source_tag="b9852",
        build_flags="cuda",
        help_text_sha256="h" * 64,
        ctx_len_configured=32768,
        parallel_slots=1,
        continuous_batching=False,
        kv_cache_quant="k=f16,v=f16",
        flash_attention="on",
        rope_scaling="model-default",
        reasoning="off",
        health_200_at="2026-07-01T00:00:00Z",
        models_response_sha256="m" * 64,
        props_response_sha256="p" * 64,
        reported_model="gemma",
        smoke_chat_sha256="s" * 64,
        owned_process_tree=["1234"],
        teardown_terminated=teardown_terminated,
        exit_code=0,
        gpu_pids_after=[] if teardown_terminated else [1234],
        server_fingerprint=fingerprint,
        model_id="gemma",
        serve_log_path=str(tmp_path / "run" / "serve.log"),
    )


def write_minimal_model(tmp_path: Path) -> Path:
    path = tmp_path / "Gemma-12B-Q4_K_M.gguf"
    path.write_bytes(minimal_gguf())
    return path


def normalized_record() -> JsonObject:
    return {
        "schema_version": "localbench.result_bundle.v1",
        "manifest": {
            "sampling": {"temperature": 0.0, "top_k": 1, "seed": 1234},
            "integrity": {"publishable": False, "blocking_reasons": [], "missing_required_fields": []},
        },
        "warnings": [],
    }


@dataclass(slots=True)
class FakeProcess:
    pid: int
    returncode: int | None
    terminated: bool = False

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode or 0


class FakeTeardownController(TeardownController):
    def __init__(self) -> None:
        self.terminated_job = False

    def terminate_job(self) -> None:
        self.terminated_job = True

    def close(self) -> None:
        return


class FakeKernel32:
    def __init__(self) -> None:
        self.info_class: int | None = None
        self.limit_flags: int | None = None
        self.assigned: tuple[int, int] | None = None
        self.terminated: tuple[int, int] | None = None
        self.closed: list[int] = []

    def CreateJobObjectW(self, security_attributes: int, name: str | None) -> int:
        return 111

    def SetInformationJobObject(self, handle: int, info_class: int, info, info_size: int) -> int:
        self.info_class = info_class
        self.limit_flags = info._obj.BasicLimitInformation.LimitFlags
        return 1

    def AssignProcessToJobObject(self, handle: int, process_handle: int) -> int:
        self.assigned = (handle, process_handle)
        return 1

    def TerminateJobObject(self, handle: int, exit_code: int) -> int:
        self.terminated = (handle, exit_code)
        return 1

    def CloseHandle(self, handle: int) -> int:
        self.closed.append(handle)
        return 1

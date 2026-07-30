from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import TracebackType
from typing import Final

from localbench._types import JsonObject, JsonValue

IM_END: Final = "<|im_end|>"
QWOPUS_TEMPLATE_TAIL: Final = """\
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
EXPECTED_INITIAL_PROMPT: Final = (
    "<|im_start|>user\n"
    "Choose the first letter.\n\n"
    "A. Alpha\nB. Beta\nC. Gamma\nD. Delta\n\n"
    "Answer with one letter.\n"
    "<|im_end|>\n"
    "<|im_start|>assistant\n"
    "<think>\n"
)


class FakeProcess:
    pid = 1234
    returncode = 0


class FakeLaunch:
    process = FakeProcess()
    job = object()
    job_handle = 1

    def close_log(self) -> None:
        return


class LlamaStub:
    def __init__(self) -> None:
        self.apply_template_requests: list[JsonObject] = []
        self.completion_requests: list[JsonObject] = []
        self.authorizations: list[str | None] = []
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> LlamaStub:
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
                    self._send({"prompt": render_prompt(payload)})
                    return
                if self.path == "/v1/chat/completions":
                    self._send(_chat_response())
                    return
                if self.path == "/v1/completions":
                    state.completion_requests.append(payload)
                    self._send(
                        _completion_response(
                            len(state.completion_requests) == 1,
                        )
                    )
                    return
                self.send_error(404)

            def log_message(
                self,
                _format: str,
                *_args: str | int | float,
            ) -> None:
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

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        assert self.server is not None
        self.server.shutdown()
        self.server.server_close()
        assert self.thread is not None
        self.thread.join(timeout=5)

    @property
    def port(self) -> int:
        assert self.server is not None
        return self.server.server_port


def render_prompt(payload: Mapping[str, JsonValue]) -> str:
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


def write_suite(path: Path) -> Path:
    path.mkdir(parents=True)
    item = {
        "question_id": 1,
        "question": "Choose the first letter.",
        "options": ["Alpha", "Beta", "Gamma", "Delta"],
        "answer": "A",
    }
    item_bytes = (json.dumps(item, separators=(",", ":")) + "\n").encode("utf-8")
    item_hash = hashlib.sha256(item_bytes).hexdigest()
    (path / "mmlu_pro_quick.jsonl").write_bytes(item_bytes)
    suite = {
        "version": "suite-renderer-blackbox-v1",
        "benches": {
            "mmlu_pro": {
                "chance_correction_baseline": 0.25,
                "decoding": {"max_tokens": 16_384, "temperature": 0},
                "itemsets": {
                    "quick": {
                        "file": "mmlu_pro_quick.jsonl",
                        "item_count": 1,
                        "sha256": item_hash,
                    }
                },
                "lane_caps": {},
                "template_text": (
                    "{question}\n\n{options}\n\nAnswer with one letter.\n"
                ),
            }
        },
    }
    (path / "suite.json").write_text(json.dumps(suite), encoding="utf-8")
    (path / "itemsets.lock.json").write_text(
        json.dumps({"files": {"mmlu_pro_quick.jsonl": {"sha256": item_hash}}}),
        encoding="utf-8",
    )
    return path


def _chat_response() -> JsonObject:
    return {
        "choices": [
            {
                "message": {"content": "ok", "reasoning_content": "probe"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
    }


def _completion_response(first_pass: bool) -> JsonObject:
    return {
        "choices": [
            {
                "text": "reasoning tokens" if first_pass else f"A{IM_END}",
                "finish_reason": "length" if first_pass else "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 8_192 if first_pass else 2,
            "total_tokens": 8_202 if first_pass else 12,
        },
    }

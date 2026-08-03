from __future__ import annotations

import json
import threading
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar, cast, final, override

from localbench._types import JsonObject, JsonValue
from localbench.check.live_server import ServerController


@final
class StubState:
    def __init__(self, model_file: Path) -> None:
        self.model_file: Path = model_file
        self.chat_template: str = "{{ messages }}"
        self.health_failures_remaining: int = 0
        self.health_calls: int = 0
        self.props_calls: int = 0
        self.requests: list[JsonObject] = []
        self.request_paths: list[str] = []
        self.completion_requests: int = 0
        self.completion_error: tuple[int, str] | None = None
        self.completion_error_after: int | None = None
        self.oversized_prompt_marker: str | None = None
        self.oversized_prompt_tokens: int = 3


class _StubHandler(BaseHTTPRequestHandler):
    state: ClassVar[StubState]

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.state.health_calls += 1
            if self.state.health_failures_remaining:
                self.state.health_failures_remaining -= 1
                self._json(503, {"status": "loading"})
            else:
                self._json(200, {"status": "ok"})
            return
        if self.path == "/props":
            self.state.props_calls += 1
            self._json(
                200,
                {
                    "backend": "CUDA",
                    "chat_template": self.state.chat_template,
                    "driver_version": "stub-driver",
                    "model_path": str(self.state.model_file.resolve()),
                    "total_slots": 1,
                },
            )
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        size = int(self.headers.get("Content-Length", "0"))
        raw_body = cast(object, json.loads(self.rfile.read(size)))
        assert isinstance(raw_body, dict)
        body = cast(JsonObject, raw_body)
        self.state.requests.append(body)
        self.state.request_paths.append(self.path)
        if self.path == "/apply-template":
            self._json(200, {"prompt": f"rendered:{body['messages']}"})
            return
        if self.path == "/tokenize":
            content = body.get("content")
            marker = self.state.oversized_prompt_marker
            count = (
                self.state.oversized_prompt_tokens
                if isinstance(content, str) and isinstance(marker, str) and marker in content
                else 3
            )
            self._json(200, {"tokens": [31, 32, 33] if count == 3 else list(range(count))})
            return
        if self.path == "/v1/completions":
            self.state.completion_requests += 1
            completion_error = self.state.completion_error
            error_after = self.state.completion_error_after
            if completion_error is not None and (
                error_after is None or self.state.completion_requests > error_after
            ):
                self._json_text(*completion_error)
                return
            stop = body.get("stop")
            if stop == ["</think>"]:
                self._sse("<think>stub reasoning", "stop", completion_tokens=32)
            else:
                assert "</think>" in str(body.get("prompt"))
                self._sse("101", "stop", completion_tokens=1)
            return
        self._json(404, {"error": "not found"})

    @override
    def log_message(self, format: str, *args: JsonValue) -> None:
        _ = format, args

    def _json(self, status: int, payload: JsonValue) -> None:
        self._json_bytes(status, json.dumps(payload).encode())

    def _json_text(self, status: int, payload: str) -> None:
        self._json_bytes(status, payload.encode())

    def _json_bytes(self, status: int, data: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        _ = self.wfile.write(data)

    def _sse(self, text: str, finish_reason: str, *, completion_tokens: int) -> None:
        payload = {
            "choices": [{"finish_reason": finish_reason, "index": 0, "text": text}],
            "usage": {
                "completion_tokens": completion_tokens,
                "prompt_tokens": 7,
                "total_tokens": completion_tokens + 7,
            },
        }
        data = f"data: {json.dumps(payload)}\n\ndata: [DONE]\n\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        _ = self.wfile.write(data)


@contextmanager
def stub_server(state: StubState) -> Generator[tuple[str, int]]:
    _StubHandler.state = state
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        assert isinstance(host, str) and isinstance(port, int)
        yield host, port
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


class FakeController:
    pid: int
    _stopped: list[int]

    def __init__(self, pid: int, stopped: list[int]) -> None:
        self.pid = pid
        self._stopped = stopped

    def poll(self) -> int | None:
        return None

    def stop(self) -> None:
        self._stopped.append(self.pid)


@final
class CrashedController(FakeController):
    @override
    def poll(self) -> int | None:
        return 23


def fake_controller_factory(pid: int, stopped: list[int]) -> ServerController:
    return FakeController(pid, stopped)

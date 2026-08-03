from __future__ import annotations

import json
import threading
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar, cast, final, override

from localbench._types import JsonObject
from localbench.check.live_http import (
    LiveHttpConfig,
    build_live_prompt_renderer,
    generate_live_item,
)


@final
class _ThinkStubState:
    def __init__(self, rendered_prompt: str) -> None:
        self.rendered_prompt = rendered_prompt
        self.requests: list[JsonObject] = []


class _ThinkStubHandler(BaseHTTPRequestHandler):
    state: ClassVar[_ThinkStubState]

    def do_POST(self) -> None:  # noqa: N802
        size = int(self.headers.get("Content-Length", "0"))
        raw_body = cast(object, json.loads(self.rfile.read(size)))
        assert isinstance(raw_body, dict)
        body = cast(JsonObject, raw_body)
        self.state.requests.append(body)
        match self.path:
            case "/apply-template":
                self._json({"prompt": self.state.rendered_prompt})
            case "/v1/completions":
                if body.get("stop") == ["</think>"]:
                    self._sse("stub reasoning", completion_tokens=17)
                else:
                    self._sse("red", completion_tokens=1)
            case "/tokenize":
                self._json({"tokens": [11, 12, 13]})
            case unreachable:
                raise AssertionError(f"unexpected stub path: {unreachable}")

    @override
    def log_message(self, format: str, *args: object) -> None:
        _ = format, args

    def _json(self, payload: JsonObject) -> None:
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        _ = self.wfile.write(data)

    def _sse(self, text: str, *, completion_tokens: int) -> None:
        payload = {
            "choices": [{"finish_reason": "stop", "index": 0, "text": text}],
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
def _think_stub(state: _ThinkStubState) -> Generator[tuple[str, int]]:
    _ThinkStubHandler.state = state
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ThinkStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        address = server.server_address
        host, port = address[0], address[1]
        assert isinstance(host, str) and isinstance(port, int)
        yield host, port
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _generate(state: _ThinkStubState) -> JsonObject:
    with _think_stub(state) as (host, port):
        config = LiveHttpConfig(
            base_url=f"http://{host}:{port}",
            api_key="stub-key",
            model_id="stub-model",
            server_start_id="stub-start",
        )
        renderer = build_live_prompt_renderer(config, {"chat_template": "{{ messages }}"})
        return generate_live_item(
            config,
            module="sanity-gates",
            item_id="budget-control-01",
            source={"prompt": "Return red."},
            prompt_renderer=renderer,
        )


def test_preopened_template_treats_phase_one_as_normal_thinking() -> None:
    # Given a rendered family template that opens thinking before generation.
    state = _ThinkStubState("rendered prompt\n<think>\n")

    # When phase one streams reasoning without repeating the opening marker.
    generation = _generate(state)

    # Then the protocol is normal and phase-one usage is retained as reasoning usage.
    assert generation["protocol_flag"] is None
    assert generation["reasoning_text"] == "stub reasoning"
    usage = generation["usage"]
    assert isinstance(usage, dict)
    assert usage["reasoning_tokens"] == 17


def test_markerless_template_and_stream_remain_protocol_absent() -> None:
    # Given a rendered template with no pre-opened think block.
    state = _ThinkStubState("rendered prompt\n")

    # When phase one also streams no opening marker.
    generation = _generate(state)

    # Then the genuinely absent-marker protocol defect remains visible.
    assert generation["protocol_flag"] == "think-markers-absent"

# THIS IS AN ADVERSARIAL TEST TOOL. Not shipped to users.
"""OpenAI-compatible answer-injection proxy for local-bench threat modeling."""

from __future__ import annotations

import argparse
import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal

import httpx
from localbench._types import JsonObject, JsonValue
from localbench._suite import read_json_object, render_benches

STRONG_MODEL_MESSAGE = (
    "inject=strong-model is not implemented in P0; it would forward to an API model "
    "and needs a key this repo does not have."
)


class StrongModelNotImplementedError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CheatProxyConfig:
    claimed_model: str = "potato-7b-q2"
    fake_tok_s: float = 35.0
    inject: Literal["answers", "strong-model"] = "answers"


@dataclass(frozen=True, slots=True)
class SuiteRecord:
    bench: str
    prompt: str
    needle: str
    answer: str | None
    source: Mapping[str, JsonValue]


class CheatProxy:
    def __init__(self, records: list[SuiteRecord], config: CheatProxyConfig, delay: Callable[[float], None] = time.sleep) -> None:
        self.records = records
        self.config = config
        self.delay = delay
        self._exact = {_normalize(record.prompt): record for record in records}

    @classmethod
    def from_suite_dir(cls, suite_dir: Path, config: CheatProxyConfig, delay: Callable[[float], None] = time.sleep) -> "CheatProxy":
        return cls(load_suite_records(suite_dir), config, delay)

    def models(self) -> JsonObject:
        return {"object": "list", "data": [{"id": self.config.claimed_model, "object": "model", "owned_by": "claimed-local-runtime"}]}

    def chat_completion(self, payload: Mapping[str, JsonValue]) -> JsonObject:
        match self.config.inject:
            case "answers":
                text = self._answer_injection_text(_user_prompt(payload))
            case "strong-model":
                raise StrongModelNotImplementedError(STRONG_MODEL_MESSAGE)
        prompt = _user_prompt(payload)
        usage = _usage(prompt, text)
        self._delay_for_tokens(usage["completion_tokens"])
        choice = {
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }
        return {"id": f"chatcmpl-cheat-{int(time.time())}", "object": "chat.completion", "created": int(time.time()), "model": self.config.claimed_model, "choices": [choice], "usage": usage}

    def handle_httpx_request(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/models"):
            return httpx.Response(200, json=self.models())
        if request.method == "POST" and request.url.path.endswith("/chat/completions"):
            try:
                payload = json.loads(request.content.decode("utf-8"))
            except json.JSONDecodeError as exc:
                return httpx.Response(400, json={"error": f"invalid JSON: {exc}"})
            if not isinstance(payload, dict):
                return httpx.Response(400, json={"error": "request body must be an object"})
            try:
                return httpx.Response(200, json=self.chat_completion(payload))
            except StrongModelNotImplementedError as exc:
                return httpx.Response(501, json={"error": str(exc)})
        return httpx.Response(404, json={"error": "not found"})

    def _answer_injection_text(self, prompt: str) -> str:
        record = self.match_prompt(prompt)
        if record is None:
            return prompt
        match record.bench:
            case "mmlu_pro":
                return f"The choices narrow to option {record.answer}.\nAnswer: {record.answer}"
            case "genmath":
                return f"Working through the arithmetic gives the final value.\n{record.answer}"
            case "ifeval":
                return _ifeval_response(record)
            case _:
                return record.answer or record.needle or prompt

    def match_prompt(self, prompt: str) -> SuiteRecord | None:
        normalized = _normalize(prompt)
        if normalized in self._exact:
            return self._exact[normalized]
        candidates = [
            record
            for record in self.records
            if record.needle and _normalize(record.needle) in normalized
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda record: len(record.needle))

    def _delay_for_tokens(self, completion_tokens: int | None) -> None:
        if self.config.fake_tok_s > 0 and completion_tokens is not None:
            self.delay(completion_tokens / self.config.fake_tok_s)


def load_suite_records(suite_dir: Path) -> list[SuiteRecord]:
    suite = read_json_object(suite_dir / "suite.json")
    records: list[SuiteRecord] = []
    seen: set[tuple[str, str]] = set()
    for tier in _suite_tiers(suite):
        warnings: list[str] = []
        for bench in render_benches("all", tier, None, suite_dir, suite, warnings):
            for source, item in zip(bench.source_items, bench.benchmark_items, strict=True):
                prompt = _prompt_from_item(item)
                key = (bench.name, prompt)
                if key in seen:
                    continue
                seen.add(key)
                records.append(SuiteRecord(bench.name, prompt, _needle(bench.name, source, prompt), _string(source.get("answer")), source))
    return records


def run_http_server(proxy: CheatProxy, port: int) -> None:
    server = ThreadingHTTPServer(("", port), _handler_class(proxy))
    print(f"cheat proxy listening on http://127.0.0.1:{port}/v1")
    server.serve_forever()


def main() -> int:
    args = _parser().parse_args()
    config = CheatProxyConfig(claimed_model=args.claimed_model, fake_tok_s=args.fake_tok_s, inject=args.inject)
    if config.inject == "strong-model":
        raise SystemExit(STRONG_MODEL_MESSAGE)
    proxy = CheatProxy.from_suite_dir(args.suite_dir, config)
    run_http_server(proxy, args.port)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag, default in (("--claimed-model", "potato-7b-q2"), ("--inject", "answers")):
        parser.add_argument(flag, default=default, choices=("answers", "strong-model") if flag == "--inject" else None)
    parser.add_argument("--suite-dir", type=Path, default=Path("suite/v0"))
    parser.add_argument("--fake-tok-s", type=float, default=35.0)
    parser.add_argument("--port", type=int, default=8001)
    return parser


def _handler_class(proxy: CheatProxy) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            status, payload = (200, proxy.models()) if self.path.rstrip("/") == "/v1/models" else (404, {"error": "not found"})
            _write_json(self, status, payload)

        def do_POST(self) -> None:
            if self.path.rstrip("/") != "/v1/chat/completions":
                _write_json(self, 404, {"error": "not found"})
                return
            length = int(self.headers.get("content-length", "0"))
            body = self.rfile.read(length)
            try:
                payload = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError as exc:
                _write_json(self, 400, {"error": f"invalid JSON: {exc}"})
                return
            if not isinstance(payload, dict):
                _write_json(self, 400, {"error": "request body must be an object"})
                return
            try:
                _write_json(self, 200, proxy.chat_completion(payload))
            except StrongModelNotImplementedError as exc:
                _write_json(self, 501, {"error": str(exc)})

    return Handler


def _needle(bench: str, item: Mapping[str, JsonValue], prompt: str) -> str:
    key = {"mmlu_pro": "question", "genmath": "statement", "ifeval": "prompt"}.get(bench)
    value = _string(item.get(key)) if key is not None else None
    return value or _string(item.get("prompt")) or _string(item.get("question")) or prompt


def _ifeval_response(record: SuiteRecord) -> str:
    ids = _string_list(record.source.get("instruction_id_list"))
    kwargs = _mapping_list(record.source.get("kwargs"))
    for index, instruction_id in enumerate(ids):
        params = kwargs[index] if index < len(kwargs) else {}
        match instruction_id:
            case "detectable_format:json_format":
                return '{"ok": true}'
            case "detectable_format:number_bullet_lists":
                return "\n".join(f"* Dialogue point {number}." for number in range(1, (_int_param(params, "num_bullets") or 3) + 1))
            case "detectable_format:number_highlighted_sections":
                return "\n".join(f"*Section {number}*\nPlan detail." for number in range(1, (_int_param(params, "num_highlights") or 5) + 1))
            case "length_constraints:number_words":
                return _words_for_constraint(params)
            case "keywords:frequency":
                keyword = _string(params.get("keyword")) or "keyword"
                return " ".join([keyword] * ((_int_param(params, "frequency") or 1) + 1))
            case _:
                continue
    return record.prompt


def _words_for_constraint(params: Mapping[str, JsonValue]) -> str:
    count = _int_param(params, "num_words") or 2
    relation = _string(params.get("relation")) or "equal to"
    match relation:
        case "equal to" | "at least":
            extra = 1 if relation == "at least" else 0
            return " ".join(f"word{index}" for index in range(1, count + extra + 1))
        case _:
            return "brief compliant answer"


def _usage(prompt: str, text: str) -> JsonObject:
    prompt_tokens = max(1, len(prompt.split()))
    completion_tokens = max(1, len(text.split()))
    return {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens}


def _user_prompt(payload: Mapping[str, JsonValue]) -> str:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            return content if isinstance(content, str) else ""
    return ""


def _suite_tiers(suite: Mapping[str, JsonValue]) -> list[str]:
    benches = suite.get("benches")
    if not isinstance(benches, dict):
        return ["quick"]
    tiers = {
        tier
        for config in benches.values()
        if isinstance(config, dict)
        for itemsets in (config.get("itemsets"),)
        if isinstance(itemsets, dict)
        for tier in itemsets
        if isinstance(tier, str)
    }
    return sorted(tiers) or ["quick"]


def _prompt_from_item(item: Mapping[str, JsonValue]) -> str:
    messages = item.get("messages")
    first = messages[0] if isinstance(messages, list) and messages else None
    content = first.get("content") if isinstance(first, dict) else None
    return content if isinstance(content, str) else ""


def _string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _string_list(value: JsonValue | None) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _mapping_list(value: JsonValue | None) -> list[Mapping[str, JsonValue]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _int_param(params: Mapping[str, JsonValue], key: str) -> int | None:
    value = params.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _write_json(handler: BaseHTTPRequestHandler, status: int, payload: JsonObject) -> None:
    encoded = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


if __name__ == "__main__":
    raise SystemExit(main())

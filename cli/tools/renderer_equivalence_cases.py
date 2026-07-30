from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Final

import typer
from localbench._suite import read_json_object, render_benches
from pydantic import JsonValue, ValidationError
from renderer_equivalence_support import (
    JSON_VALUE,
    Config,
    HarnessError,
    RenderCase,
)

_SYSTEM = "Follow the benchmark instructions exactly."
_TOOLS: Final[list[JsonValue]] = [
    {
        "type": "function",
        "function": {
            "name": "lookup",
            "description": "Return a benchmark lookup result.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }
]


def _static_cases(config: Config) -> list[RenderCase]:
    suite = read_json_object(config.suite_cache / "suite.json")
    warnings: list[str] = []
    benches = render_benches(
        "all",
        config.tier,
        None,
        config.suite_cache,
        suite,
        warnings,
    )
    for warning in warnings:
        typer.echo(f"suite warning: {warning}", err=True)
    cases = [
        RenderCase(
            f"static-{bench.name}-{item['id']}",
            [dict(message) for message in item["messages"]],
        )
        for bench in benches
        for item in bench.benchmark_items
    ]
    if len(cases) < 3:
        raise HarnessError("suite cache produced fewer than three static message sets")
    return cases


def _json_values(path: Path) -> list[JsonValue]:
    data = path.read_bytes()
    try:
        return [JSON_VALUE.validate_json(data)]
    except ValidationError:
        values: list[JsonValue] = []
        for line_number, line in enumerate(data.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                values.append(JSON_VALUE.validate_json(line))
            except ValidationError as error:
                raise HarnessError(f"invalid JSONL at {path}:{line_number}") from error
        return values


def _agentic_requests(value: JsonValue) -> Iterator[dict[str, JsonValue]]:
    if isinstance(value, list):
        for child in value:
            yield from _agentic_requests(child)
        return
    if not isinstance(value, dict):
        return
    requests = value.get("model_turn_requests")
    if isinstance(requests, list):
        for request in requests:
            if isinstance(request, dict):
                yield request
        return
    if isinstance(value.get("messages"), list):
        yield value
        return
    for child in value.values():
        yield from _agentic_requests(child)


def _required_messages(request: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    messages = request.get("messages")
    if not isinstance(messages, list):
        raise HarnessError("agentic request omitted messages")
    checked: list[dict[str, JsonValue]] = []
    for message in messages:
        if not isinstance(message, dict):
            raise HarnessError("agentic request contains a non-object message")
        role = message.get("role")
        content = message.get("content")
        if not isinstance(role, str) or not isinstance(content, str):
            raise HarnessError("agentic message requires string role and content")
        checked.append(dict(message))
    return checked


def _shaped_static_cases(static: list[RenderCase]) -> list[RenderCase]:
    prompt_a = static[0].messages[0]["content"]
    prompt_b = static[1].messages[0]["content"]
    prompt_c = static[2].messages[0]["content"]
    if not all(isinstance(value, str) for value in (prompt_a, prompt_b, prompt_c)):
        raise HarnessError("static suite messages require text content")
    return [
        RenderCase(
            "system-user",
            [{"role": "system", "content": _SYSTEM}, *static[0].messages],
        ),
        RenderCase(
            "multi-turn",
            [
                *static[1].messages,
                {"role": "assistant", "content": "Acknowledged."},
                {"role": "user", "content": prompt_c},
            ],
        ),
        RenderCase(
            "tool-declaration-result",
            [
                {"role": "user", "content": prompt_a},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "arguments": '{"query":"benchmark"}',
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "name": "lookup",
                    "content": '{"result":"available"}',
                },
                {"role": "user", "content": prompt_b},
            ],
            tools=_TOOLS,
        ),
        RenderCase(
            "assistant-continuation",
            [
                *static[2].messages,
                {
                    "role": "assistant",
                    "content": "Working through the benchmark",
                },
            ],
            add_generation_prompt=False,
            continue_final_message=True,
        ),
    ]


def load_cases(config: Config) -> list[RenderCase]:
    static = _static_cases(config)
    shaped = _shaped_static_cases(static)
    requests = (
        request
        for value in _json_values(config.agentic_trace)
        for request in _agentic_requests(value)
    )
    agentic = [
        RenderCase(f"agentic-{index:03d}", _required_messages(request))
        for index, request in enumerate(requests, start=1)
        if index <= config.samples
    ]
    if not agentic:
        raise HarnessError("agentic trace contained no model_turn_requests")
    return [*static, *shaped, *agentic]

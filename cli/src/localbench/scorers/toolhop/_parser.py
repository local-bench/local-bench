from __future__ import annotations

import ast
import json
import re
from collections.abc import Mapping
from typing import Final

from localbench.scorers.toolhop._types import JsonObject, JsonValue, ParsedCall, ToolTrace

_FENCE_RE: Final = re.compile(r"```[a-zA-Z0-9_+-]*\s*\n?(?P<body>.*?)```", re.DOTALL)


def decode_tool_trace(response_text: str) -> ToolTrace | None:
    if not response_text.strip():
        return None
    source = _unfenced(response_text.strip())
    parsed = _decode_json(source)
    if parsed is None:
        parsed = _decode_literal(source)
    return _coerce_trace(parsed)


def parse_call(source: str) -> ParsedCall | None:
    try:
        parsed = ast.parse(source.strip(), mode="eval")
    except SyntaxError:
        return None
    if not isinstance(parsed.body, ast.Call) or not isinstance(parsed.body.func, ast.Name):
        return None
    args: list[JsonValue] = []
    for arg in parsed.body.args:
        value = _literal(arg)
        if value is _MISSING:
            return None
        args.append(value)
    kwargs: JsonObject = {}
    for keyword in parsed.body.keywords:
        if keyword.arg is None:
            return None
        value = _literal(keyword.value)
        if value is _MISSING:
            return None
        kwargs[keyword.arg] = value
    return ParsedCall(
        function_name=parsed.body.func.id,
        args=tuple(args),
        kwargs=kwargs,
        raw=source,
    )


def encode_trace(trace: ToolTrace) -> str:
    return json.dumps(trace, ensure_ascii=False, separators=(",", ":"))


def _unfenced(source: str) -> str:
    fence = _FENCE_RE.fullmatch(source)
    return (fence.group("body") if fence else source).strip("`\n ")


def _decode_json(source: str) -> JsonValue | None:
    try:
        value = json.loads(source)
    except json.JSONDecodeError:
        return None
    return value if _is_json_value(value) else None


def _decode_literal(source: str) -> JsonValue | None:
    try:
        value = ast.literal_eval(source)
    except (SyntaxError, ValueError):
        return None
    return _jsonify(value)


def _coerce_trace(value: JsonValue | None) -> ToolTrace | None:
    if isinstance(value, dict):
        for key in ("calls", "trace", "tool_calls"):
            if key in value:
                value = value[key]
                break
    if not isinstance(value, list):
        return None
    calls: ToolTrace = []
    for item in value:
        if isinstance(item, str):
            calls.append(item)
            continue
        if isinstance(item, dict):
            call = _structured_call(item)
            if call is None:
                return None
            calls.append(call)
            continue
        return None
    return calls


def _structured_call(item: JsonObject) -> str | None:
    name_value: JsonValue | None = item.get("name")
    args_value: JsonValue | None = item.get("arguments", item.get("args", {}))
    function_value = item.get("function")
    if isinstance(function_value, dict):
        name_value = function_value.get("name")
        args_value = function_value.get("arguments", {})
    if not isinstance(name_value, str) or not name_value:
        return None
    if isinstance(args_value, str):
        args_value = _decode_json(args_value)
    if args_value is None:
        args_value = {}
    if not isinstance(args_value, dict):
        return None
    args = ",".join(
        f"{key}={json.dumps(value, ensure_ascii=False)}"
        for key, value in sorted(args_value.items())
    )
    return f"{name_value}({args})"


class _Missing:
    pass


_MISSING: Final = _Missing()


def _literal(node: ast.expr) -> JsonValue | _Missing:
    if isinstance(node, ast.Constant):
        return _jsonify(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _literal(node.operand)
        if isinstance(inner, int | float):
            return -inner
        return _MISSING
    if isinstance(node, ast.Name):
        lowered = node.id.lower()
        if lowered in {"true", "false", "none", "null"}:
            return {"true": True, "false": False, "none": None, "null": None}[lowered]
        return _MISSING
    if isinstance(node, ast.List | ast.Tuple):
        values = [_literal(item) for item in node.elts]
        if any(isinstance(value, _Missing) for value in values):
            return _MISSING
        return [value for value in values if not isinstance(value, _Missing)]
    if isinstance(node, ast.Dict):
        output: JsonObject = {}
        for key_node, value_node in zip(node.keys, node.values, strict=True):
            if key_node is None:
                return _MISSING
            key = _literal(key_node)
            value = _literal(value_node)
            if isinstance(key, _Missing) or isinstance(value, _Missing):
                return _MISSING
            output[str(key)] = value
        return output
    return _MISSING


def _jsonify(value: object) -> JsonValue | None:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, tuple | list):
        return [_jsonify(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _jsonify(item) for key, item in value.items()}
    return None


def _is_json_value(value: object) -> bool:
    if isinstance(value, str | int | float | bool) or value is None:
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    return False

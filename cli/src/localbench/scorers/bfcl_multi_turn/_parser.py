from __future__ import annotations

import ast
import json
import re
from collections.abc import Mapping
from typing import Final

from localbench.scorers.bfcl_multi_turn._types import ActionTrace, JsonValue, ParsedCall

_FENCE_RE: Final = re.compile(r"```[a-zA-Z0-9_+-]*\s*\n?(?P<body>.*?)```", re.DOTALL)


def decode_action_trace(response_text: str) -> ActionTrace | None:
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
    if not isinstance(parsed.body, ast.Call):
        return None
    func_name, class_name = _function_name(parsed.body.func)
    if func_name is None:
        return None
    args: list[JsonValue] = []
    for arg in parsed.body.args:
        value = _literal(arg)
        if value is _MISSING:
            return None
        args.append(value)
    kwargs: dict[str, JsonValue] = {}
    for keyword in parsed.body.keywords:
        if keyword.arg is None:
            return None
        value = _literal(keyword.value)
        if value is _MISSING:
            return None
        kwargs[keyword.arg] = value
    return ParsedCall(
        function_name=func_name,
        class_name=class_name,
        args=tuple(args),
        kwargs=kwargs,
        raw=source,
    )


def encode_trace(trace: ActionTrace) -> str:
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


def _coerce_trace(value: JsonValue | None) -> ActionTrace | None:
    if isinstance(value, dict):
        value = value.get("turns")
    if not isinstance(value, list):
        return None
    if all(isinstance(item, str) for item in value):
        return [[str(item) for item in value]]
    trace: ActionTrace = []
    for turn in value:
        if not isinstance(turn, list) or not all(isinstance(call, str) for call in turn):
            return None
        trace.append([str(call) for call in turn])
    return trace


def _function_name(node: ast.expr) -> tuple[str | None, str | None]:
    if isinstance(node, ast.Name):
        return node.id, None
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return node.attr, node.value.id
    return None, None


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
        return node.id
    if isinstance(node, ast.List | ast.Tuple):
        values = [_literal(item) for item in node.elts]
        if any(isinstance(value, _Missing) for value in values):
            return _MISSING
        return [value for value in values if not isinstance(value, _Missing)]
    if isinstance(node, ast.Dict):
        output: dict[str, JsonValue] = {}
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

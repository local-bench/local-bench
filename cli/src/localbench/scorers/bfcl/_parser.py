from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from typing import Final

from localbench.scorers.bfcl._types import AstCall, AstValue

_BIN_OPS: Final[dict[type[ast.operator], Callable[[int | float, int | float], int | float]]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


def decode_bfcl_response(response_text: str) -> list[AstCall] | None:
    if not isinstance(response_text, str) or not response_text.strip():
        return None
    source = response_text.strip("`\n ")
    if not source.startswith("["):
        source = "[" + source
    if not source.endswith("]"):
        source = source + "]"
    try:
        parsed = ast.parse(source, mode="eval")
    except SyntaxError:
        return None
    if not isinstance(parsed.body, ast.List):
        return None
    calls: list[AstCall] = []
    for elem in parsed.body.elts:
        if not isinstance(elem, ast.Call):
            return None
        call = _resolve_call(elem)
        if call is None:
            return None
        calls.append(call)
    return calls


def _resolve_call(elem: ast.Call) -> AstCall | None:
    function_name = _function_name(elem.func)
    if function_name is None:
        return None
    args: dict[str, AstValue] = {}
    for keyword in elem.keywords:
        if keyword.arg is None:
            return None
        value = _resolve_value(keyword.value)
        if value is None:
            return None
        args[keyword.arg] = value
    return {function_name: args}


def _function_name(func: ast.expr) -> str | None:
    parts: list[str] = []
    current = func
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _resolve_value(value: ast.expr) -> AstValue | None:
    if isinstance(value, ast.Constant):
        if value.value is Ellipsis:
            return "..."
        if isinstance(value.value, str | int | float | bool | type(None)):
            return value.value
        return None
    if isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.USub):
        inner = _resolve_value(value.operand)
        if isinstance(inner, int | float):
            return -inner
        return None
    if isinstance(value, ast.List):
        return [_resolve_value(item) for item in value.elts]
    if isinstance(value, ast.Tuple):
        resolved = [_resolve_value(item) for item in value.elts]
        if any(item is None for item in resolved):
            return None
        return tuple(resolved)
    if isinstance(value, ast.Dict):
        return _resolve_dict(value)
    if isinstance(value, ast.Name):
        # JSON/JS-style literals (true/false/null) parse as bare names under Python's
        # grammar; map them to Python values so a model that emits lowercase booleans
        # isn't mis-scored (the name would otherwise coerce to a string that can never
        # match the expected bool/None). Genuine identifiers fall through unchanged.
        return {"true": True, "false": False, "null": None, "none": None}.get(
            value.id.lower(), value.id
        )
    if isinstance(value, ast.Call):
        if not value.keywords:
            return ast.unparse(value)
        return _resolve_call(value)
    if isinstance(value, ast.BinOp):
        return _resolve_binop(value)
    if isinstance(value, ast.Lambda | ast.Subscript):
        return ast.unparse(value)
    return None


def _resolve_dict(value: ast.Dict) -> dict[str, AstValue] | None:
    output: dict[str, AstValue] = {}
    for key, item in zip(value.keys, value.values, strict=True):
        if key is None:
            return None
        resolved_key = _resolve_value(key)
        resolved_value = _resolve_value(item)
        if resolved_key is None or resolved_value is None:
            return None
        output[str(resolved_key)] = resolved_value
    return output


def _resolve_binop(value: ast.BinOp) -> AstValue | None:
    left = _resolve_value(value.left)
    right = _resolve_value(value.right)
    op = _BIN_OPS.get(type(value.op))
    if op is None or not isinstance(left, int | float) or not isinstance(right, int | float):
        return ast.unparse(value)
    try:
        return op(left, right)
    except ArithmeticError:
        return ast.unparse(value)

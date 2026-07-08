"""AST policy gate for generated BigCodeBench Python.

This is defense-in-depth, not a proof of safety. A determined adversary can still
try obfuscation through `getattr`, dynamic imports, or `eval`; the gate is paired
with the trusted completion sentinel in `program.py` so simple in-process grading
forgery is rejected before execution or fails after the suite runs.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

AST_GATE_REV: Final = "bigcodebench-ast-gate-v2"

ASTGateFailure: TypeAlias = Literal[
    "syntax_error",
    "forbidden_reference",
    "forbidden_top_level_statement",
]

_FORBIDDEN_OS_ATTRS: Final = frozenset({"_exit", "kill", "abort"})


@dataclass(frozen=True, slots=True)
class ASTGateResult:
    accepted: bool
    failure: ASTGateFailure | None = None
    detail: str | None = None


def check_ast_gate(sanitized_code: str) -> ASTGateResult:
    try:
        module = ast.parse(sanitized_code)
    except SyntaxError as exc:
        return ASTGateResult(False, "syntax_error", f"line {exc.lineno}: {exc.msg}")

    forbidden = _forbidden_reference(module)
    if forbidden is not None:
        return ASTGateResult(False, "forbidden_reference", forbidden)

    top_level = _forbidden_top_level(module.body)
    if top_level is not None:
        return ASTGateResult(False, "forbidden_top_level_statement", top_level)

    return ASTGateResult(True)


def _forbidden_reference(module: ast.Module) -> str | None:
    module_aliases: dict[str, str] = {}
    for node in ast.walk(module):
        match node:
            case ast.Import(names=names):
                for alias in names:
                    root = alias.name.split(".", maxsplit=1)[0]
                    bound = alias.asname or root
                    if root == "atexit":
                        return "import atexit"
                    if root == "signal":
                        return "import signal"
                    if root in {"os", "sys"}:
                        module_aliases[bound] = root
            case ast.ImportFrom(module=raw_module, names=names) if raw_module is not None:
                module_name = raw_module.split(".", maxsplit=1)[0]
                if module_name in {"atexit", "signal"}:
                    return f"from {module_name} import ..."
                for alias in names:
                    if module_name == "os" and alias.name in _FORBIDDEN_OS_ATTRS:
                        return f"from os import {alias.name}"
                    if module_name == "sys" and alias.name == "exit":
                        return "from sys import exit"
            case ast.Attribute(value=ast.Name(id=name), attr=attr):
                module_name = module_aliases.get(name, name)
                if module_name == "os" and attr in _FORBIDDEN_OS_ATTRS:
                    return f"os.{attr}"
                if module_name == "sys" and attr == "exit":
                    return "sys.exit"
                if module_name == "signal":
                    return f"signal.{attr}"
                if module_name == "atexit":
                    return f"atexit.{attr}"
            case ast.Name(id="atexit"):
                return "atexit"
            # Defense-in-depth: forbid the process-exit builtins and SystemExit references
            # (a `raise SystemExit(0)` / `exit()` from a helper was the demonstrated forgery's
            # early-exit primitive). The invert-control driver already scores any exit during
            # untrusted execution as a failure; blocking these gives an earlier, cleaner
            # conformance signal. Load context only, so a variable merely named `exit` may still
            # be assigned. No canonical BigCodeBench-Hard solution references these.
            case ast.Name(id="exit" | "quit" | "SystemExit" as name, ctx=ast.Load()):
                return name
            case _:
                continue
    return None


def _forbidden_top_level(statements: list[ast.stmt]) -> str | None:
    for statement in statements:
        detail = _top_level_violation(statement)
        if detail is not None:
            return detail
    return None


def _top_level_violation(statement: ast.stmt) -> str | None:
    match statement:
        case ast.Import() | ast.ImportFrom() | ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef():
            return None
        case ast.Pass():
            return None
        case ast.Expr(value=ast.Constant()):
            return None
        case ast.Expr(value=ast.Call() as call):
            if _is_allowed_top_level_call(call):
                return None
            return "top-level Expr is not allowed"
        case ast.Assign(targets=targets):
            if all(_is_plain_name(target) for target in targets):
                return None
            return "top-level assignment target is not a plain name"
        case ast.AnnAssign(target=target):
            if _is_plain_name(target):
                return None
            return "top-level annotated assignment target is not a plain name"
        case ast.If(test=test, body=body, orelse=orelse):
            if not _is_name_guard(test):
                return "top-level if is not an if __name__ guard"
            body_violation = _forbidden_top_level(body)
            if body_violation is not None:
                return body_violation
            return _forbidden_top_level(orelse)
        case _:
            return f"top-level {type(statement).__name__} is not allowed"


def _is_plain_name(node: ast.expr) -> bool:
    match node:
        case ast.Name():
            return True
        case _:
            return False


def _is_name_guard(test: ast.expr) -> bool:
    match test:
        case ast.Compare(
            left=ast.Name(id="__name__"),
            ops=[ast.Eq()],
            comparators=[ast.Constant(value="__main__")],
        ):
            return True
        case ast.Compare(
            left=ast.Constant(value="__main__"),
            ops=[ast.Eq()],
            comparators=[ast.Name(id="__name__")],
        ):
            return True
        case _:
            return False


def _is_allowed_top_level_call(call: ast.Call) -> bool:
    match call:
        case ast.Call(
            func=ast.Attribute(value=ast.Name(id="nltk"), attr="download"),
            args=[ast.Constant(value=str())],
        ):
            return True
        case _:
            return False

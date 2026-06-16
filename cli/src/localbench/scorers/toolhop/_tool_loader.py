from __future__ import annotations

import ast
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from localbench.scorers.toolhop._types import JsonValue

ALLOWED_IMPORTS: Final[frozenset[str]] = frozenset(
    {
        "base64",
        "binascii",
        "calendar",
        "cmath",
        "collections",
        "csv",
        "datetime",
        "fractions",
        "functools",
        "io",
        "itertools",
        "json",
        "math",
        "numbers",
        "re",
        "statistics",
        "string",
        "unicodedata",
        "xml",
    },
)
FORBIDDEN_IMPORTS: Final[frozenset[str]] = frozenset(
    {
        "builtins",
        "ctypes",
        "importlib",
        "os",
        "pathlib",
        "requests",
        "shutil",
        "socket",
        "subprocess",
        "sys",
        "time",
        "urllib",
    },
)
FORBIDDEN_CALLS: Final[frozenset[str]] = frozenset(
    {"__import__", "compile", "eval", "exec", "getattr", "globals", "input", "locals", "open", "vars"}
)
FORBIDDEN_ATTRS: Final[frozenset[str]] = frozenset(
    {"now", "popen", "sleep", "system", "today", "utcnow"}
)
FORBIDDEN_NODES: Final[tuple[type[ast.AST], ...]] = (
    ast.AsyncFunctionDef,
    ast.Await,
    ast.ClassDef,
    ast.Delete,
    ast.Global,
    ast.Nonlocal,
    ast.With,
    ast.Yield,
    ast.YieldFrom,
)


class ToolLoadError(RuntimeError):
    pass


ToolFunction = Callable[..., JsonValue]


@dataclass(frozen=True, slots=True)
class LoadedTools:
    functions: dict[str, ToolFunction]
    allowed_names: frozenset[str]


def load_tools(item: Mapping[str, JsonValue]) -> LoadedTools:
    allowed_names = frozenset(_tool_names(item))
    if not allowed_names:
        raise ToolLoadError("item does not declare any tools")
    namespace = _namespace()
    for source in _function_sources(item):
        tree = _validated_module(source)
        code = compile(tree, "<toolhop-tool>", "exec")
        exec(code, namespace)
    functions: dict[str, ToolFunction] = {}
    for name in allowed_names:
        value = namespace.get(name)
        if not callable(value):
            raise ToolLoadError(f"tool implementation missing: {name}")
        functions[name] = value
    return LoadedTools(functions=functions, allowed_names=allowed_names)


def function_names_from_source(source: str) -> list[str]:
    tree = ast.parse(source)
    return [stmt.name for stmt in tree.body if isinstance(stmt, ast.FunctionDef)]


def validate_tool_source(source: str) -> list[str]:
    try:
        _validated_module(source)
    except (SyntaxError, ToolLoadError) as error:
        return [str(error)]
    return []


def _validated_module(source: str) -> ast.Module:
    tree = ast.parse(source)
    kept: list[ast.stmt] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Import | ast.ImportFrom | ast.FunctionDef):
            kept.append(stmt)
        elif isinstance(stmt, ast.ClassDef):
            raise ToolLoadError("forbidden_node:ClassDef")
    if not any(isinstance(stmt, ast.FunctionDef) for stmt in kept):
        raise ToolLoadError("tool source has no function definition")
    for node in ast.walk(ast.Module(body=kept, type_ignores=[])):
        _validate_node(node)
    return ast.fix_missing_locations(ast.Module(body=kept, type_ignores=[]))


def _validate_node(node: ast.AST) -> None:
    if isinstance(node, FORBIDDEN_NODES):
        raise ToolLoadError(f"forbidden_node:{type(node).__name__}")
    if isinstance(node, ast.Import):
        for alias in node.names:
            _validate_import_root(alias.name)
    elif isinstance(node, ast.ImportFrom):
        if node.level != 0:
            raise ToolLoadError("relative_import")
        _validate_import_root(node.module or "")
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            raise ToolLoadError(f"forbidden_call:{node.func.id}")
        if isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_ATTRS:
            raise ToolLoadError(f"forbidden_attr:{node.func.attr}")
    elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
        raise ToolLoadError(f"forbidden_attr:{node.attr}")


def _validate_import_root(module: str) -> None:
    root = module.split(".", 1)[0]
    if root in FORBIDDEN_IMPORTS:
        raise ToolLoadError(f"unsafe_module:{root}")
    if root not in ALLOWED_IMPORTS:
        raise ToolLoadError(f"unsupported_module:{root}")


def _namespace() -> dict[str, object]:
    return {
        "__builtins__": {
            "__import__": _limited_import,
            "ArithmeticError": ArithmeticError,
            "Exception": Exception,
            "KeyError": KeyError,
            "RuntimeError": RuntimeError,
            "TypeError": TypeError,
            "ValueError": ValueError,
            "abs": abs,
            "all": all,
            "any": any,
            "bin": bin,
            "bool": bool,
            "chr": chr,
            "complex": complex,
            "dict": dict,
            "divmod": divmod,
            "enumerate": enumerate,
            "filter": filter,
            "float": float,
            "format": format,
            "hex": hex,
            "int": int,
            "isinstance": isinstance,
            "len": len,
            "list": list,
            "map": map,
            "max": max,
            "min": min,
            "ord": ord,
            "pow": pow,
            "print": _discard_print,
            "range": range,
            "round": round,
            "set": set,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "zip": zip,
        },
    }


def _limited_import(
    name: str,
    globals_: object = None,
    locals_: object = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> object:
    if level != 0:
        raise ToolLoadError("relative_import")
    _validate_import_root(name)
    return __import__(name, globals_, locals_, fromlist, level)


def _discard_print(*_args: object, **_kwargs: object) -> None:
    return None


def _function_sources(item: Mapping[str, JsonValue]) -> list[str]:
    value = item.get("functions")
    if not isinstance(value, list):
        raise ToolLoadError("functions must be a list")
    return [source for source in value if isinstance(source, str)]


def _tool_names(item: Mapping[str, JsonValue]) -> list[str]:
    tools = item.get("tools")
    if not isinstance(tools, dict):
        return []
    names: list[str] = []
    for tool in tools.values():
        if isinstance(tool, dict) and isinstance(tool.get("name"), str):
            names.append(tool["name"])
    return names

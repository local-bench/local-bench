from __future__ import annotations

import inspect
import json
import sys
import time
from collections.abc import Callable, Mapping
from typing import Final

from localbench.scorers.bfcl_multi_turn._sandbox import (
    ConstrainedExecutionError,
    blocked_side_effects,
)
from localbench.scorers.toolhop._parser import parse_call
from localbench.scorers.toolhop._tool_loader import ALLOWED_IMPORTS, ToolLoadError, load_tools
from localbench.scorers.toolhop._types import FailureKind, JsonValue, ParsedCall, TraceExecution

DEFAULT_TIMEOUT_SECONDS: Final = 2.0
DEFAULT_MAX_STEPS: Final = 9
DEFAULT_MAX_LINE_EVENTS: Final = 20_000


def execute_toolhop_trace(
    *,
    item: Mapping[str, JsonValue],
    trace: list[str],
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_steps: int = DEFAULT_MAX_STEPS,
    max_line_events: int = DEFAULT_MAX_LINE_EVENTS,
) -> TraceExecution:
    started = time.perf_counter()
    if timeout_seconds <= 0:
        return TraceExecution([], [], FailureKind.TIMEOUT, "execution budget exhausted")
    if len(trace) > max_steps:
        return TraceExecution(trace, [], FailureKind.TIMEOUT, "step limit exceeded")
    try:
        loaded = load_tools(item)
    except (SyntaxError, ToolLoadError) as error:
        return TraceExecution(trace, [], FailureKind.TOOL_EXEC_ERROR, str(error))
    outputs: list[JsonValue] = []
    for source in trace:
        if _timed_out(started, timeout_seconds):
            return TraceExecution(trace, outputs, FailureKind.TIMEOUT, "item timed out")
        parsed = parse_call(source)
        if parsed is None:
            return TraceExecution(trace, outputs, FailureKind.MALFORMED_CALL, source)
        if parsed.function_name not in loaded.allowed_names:
            return TraceExecution(trace, outputs, FailureKind.WRONG_TOOL, source)
        function = loaded.functions.get(parsed.function_name)
        if function is None:
            return TraceExecution(trace, outputs, FailureKind.WRONG_TOOL, source)
        try:
            inspect.signature(function).bind(*parsed.args, **parsed.kwargs)
        except TypeError as error:
            return TraceExecution(trace, outputs, FailureKind.WRONG_ARGS, str(error))
        output = _invoke(
            function,
            parsed,
            started=started,
            timeout_seconds=timeout_seconds,
            max_line_events=max_line_events,
        )
        if isinstance(output, _ToolFailure):
            return TraceExecution(trace, outputs, output.failure_kind, output.message)
        outputs.append(output)
    return TraceExecution(trace, outputs)


class _ToolFailure:
    def __init__(self, failure_kind: FailureKind, message: str) -> None:
        self.failure_kind = failure_kind
        self.message = message


def _invoke(
    function: Callable[..., JsonValue],
    parsed: ParsedCall,
    *,
    started: float,
    timeout_seconds: float,
    max_line_events: int,
) -> JsonValue | _ToolFailure:
    limiter = _LineLimiter(started, timeout_seconds, max_line_events)
    previous_trace = sys.gettrace()
    try:
        with blocked_side_effects(allowed_imports=ALLOWED_IMPORTS):
            sys.settrace(limiter.trace)
            result = function(*parsed.args, **parsed.kwargs)
    except TimeoutError as error:
        return _ToolFailure(FailureKind.TIMEOUT, str(error))
    except (
        ArithmeticError,
        AttributeError,
        ConstrainedExecutionError,
        ImportError,
        KeyError,
        NameError,
        RecursionError,
        RuntimeError,
        ToolLoadError,
        TypeError,
        ValueError,
    ) as error:
        return _ToolFailure(FailureKind.TOOL_EXEC_ERROR, str(error))
    finally:
        sys.settrace(previous_trace)
    return _jsonify_output(result)


class _LineLimiter:
    def __init__(self, started: float, timeout_seconds: float, max_line_events: int) -> None:
        self._started = started
        self._timeout_seconds = timeout_seconds
        self._max_line_events = max_line_events
        self._line_events = 0

    def trace(self, frame: object, event: str, arg: object) -> object:
        if event == "line":
            self._line_events += 1
            if self._line_events > self._max_line_events:
                raise TimeoutError("tool line-event limit exceeded")
            if _timed_out(self._started, self._timeout_seconds):
                raise TimeoutError("item timed out")
        return self.trace


def _jsonify_output(value: object) -> JsonValue:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, tuple | list | set):
        return [_jsonify_output(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonify_output(item) for key, item in value.items()}
    isoformat_method = getattr(value, "isoformat", None)
    if callable(isoformat_method):
        isoformat = isoformat_method()
        if isinstance(isoformat, str):
            return isoformat
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError):
        return repr(value)


def _timed_out(started: float, timeout_seconds: float) -> bool:
    return time.perf_counter() - started > timeout_seconds

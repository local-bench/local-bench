from __future__ import annotations

import builtins
import inspect
import json
import time
from collections import Counter
from collections.abc import Callable, Mapping
from typing import Final

from localbench.scorers.bfcl_multi_turn._backend import load_backend_instances, public_method_map
from localbench.scorers.bfcl_multi_turn._parser import parse_call
from localbench.scorers.bfcl_multi_turn._sandbox import blocked_side_effects
from localbench.scorers.bfcl_multi_turn._types import (
    ActionTrace,
    FailureKind,
    JsonObject,
    JsonValue,
    ParsedCall,
    StateComparison,
    TraceExecution,
    TurnExecution,
)

DEFAULT_TIMEOUT_SECONDS: Final = 2.0
DEFAULT_MAX_STEPS: Final = 64


def execute_trace(
    *,
    item: Mapping[str, JsonValue],
    trace: ActionTrace,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> TraceExecution:
    started = time.perf_counter()
    if timeout_seconds <= 0:
        return TraceExecution([], {}, FailureKind.TIMEOUT, "execution budget exhausted")
    env = _ExecutionEnv.from_item(item)
    responses_by_turn: list[list[str]] = []
    steps = 0
    for turn in trace:
        if _timed_out(started, timeout_seconds):
            return TraceExecution(responses_by_turn, env.state(), FailureKind.TIMEOUT, "item timed out")
        steps += len(turn)
        if steps > max_steps:
            return TraceExecution(responses_by_turn, env.state(), FailureKind.TIMEOUT, "step limit exceeded")
        result = env.execute_turn(turn)
        responses_by_turn.append(result.responses)
        if result.failure_kind is not None:
            return TraceExecution(responses_by_turn, env.state(), result.failure_kind, result.message)
    return TraceExecution(responses_by_turn, env.state())


def score_trace_against_gold(
    *,
    item: Mapping[str, JsonValue],
    model_trace: ActionTrace,
    gold_trace: ActionTrace,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> tuple[bool, FailureKind | None, JsonObject]:
    started = time.perf_counter()
    model_env = _ExecutionEnv.from_item(item)
    gold_env = _ExecutionEnv.from_item(item)
    model_responses: list[str] = []
    responses_by_turn: list[list[str]] = []
    steps = 0
    turn_count = max(len(model_trace), len(gold_trace))
    for turn_index in range(turn_count):
        if _timed_out(started, timeout_seconds):
            return False, FailureKind.TIMEOUT, _details(model_env, responses_by_turn)
        model_turn = model_trace[turn_index] if turn_index < len(model_trace) else []
        gold_turn = gold_trace[turn_index] if turn_index < len(gold_trace) else []
        steps += len(model_turn) + len(gold_turn)
        if steps > max_steps:
            return False, FailureKind.TIMEOUT, _details(model_env, responses_by_turn)
        model_result = model_env.execute_turn(model_turn)
        responses_by_turn.append(model_result.responses)
        model_responses.extend(model_result.responses)
        if model_result.failure_kind is not None:
            return False, model_result.failure_kind, _details(model_env, responses_by_turn)
        gold_result = gold_env.execute_turn(gold_turn)
        if gold_result.failure_kind is not None:
            return False, FailureKind.WRONG_STATE, _details(model_env, responses_by_turn)
        if not gold_turn:
            if model_turn:
                return False, FailureKind.WRONG_FINAL_RESPONSE, _details(model_env, responses_by_turn)
            continue
        if not model_turn:
            return False, FailureKind.WRONG_FINAL_RESPONSE, _details(model_env, responses_by_turn)
        state_check = compare_state(model_env.state(), gold_env.state())
        if not state_check.valid:
            details = _details(model_env, responses_by_turn)
            details["state_differences"] = state_check.differences
            return False, FailureKind.WRONG_STATE, details
        if not _contains_all(model_responses, gold_result.responses):
            return False, FailureKind.WRONG_FINAL_RESPONSE, _details(model_env, responses_by_turn)
    return True, None, _details(model_env, responses_by_turn)


def compare_state(model_state: Mapping[str, JsonValue], gold_state: Mapping[str, JsonValue]) -> StateComparison:
    differences: dict[str, JsonValue] = {}
    for class_name, gold_value in gold_state.items():
        model_value = model_state.get(class_name)
        if model_value != gold_value:
            differences[class_name] = {"model": model_value, "ground_truth": gold_value}
    return StateComparison(valid=not differences, differences=differences)


class _ExecutionEnv:
    def __init__(
        self,
        instances: dict[str, object],
        methods: dict[str, tuple[str, Callable[..., object]]],
        available_functions: set[str],
    ) -> None:
        self._instances = instances
        self._methods = methods
        self._available_functions = available_functions

    @classmethod
    def from_item(cls, item: Mapping[str, JsonValue]) -> "_ExecutionEnv":
        involved = _str_list(item.get("involved_classes"))
        config = item.get("initial_config")
        instances = load_backend_instances(
            involved,
            config if isinstance(config, dict) else {},
            long_context=_category(item).endswith("long_context"),
        )
        return cls(instances, public_method_map(instances), _available_functions(item))

    def execute_turn(self, calls: list[str]) -> TurnExecution:
        responses: list[str] = []
        for source in calls:
            parsed = parse_call(source)
            if parsed is None:
                return TurnExecution(responses, FailureKind.MALFORMED_CALL, source)
            failure = self._validate_call(parsed)
            if failure is not None:
                return TurnExecution(responses, failure, source)
            class_name, method = self._methods[parsed.function_name]
            if parsed.class_name is not None and parsed.class_name != class_name:
                return TurnExecution(responses, FailureKind.WRONG_TOOL, source)
            try:
                inspect.signature(method).bind(*parsed.args, **parsed.kwargs)
            except TypeError as error:
                return TurnExecution(responses, FailureKind.WRONG_ARGS, str(error))
            responses.append(_invoke(method, parsed))
        return TurnExecution(responses)

    def state(self) -> JsonObject:
        return {class_name: _jsonify_public(instance) for class_name, instance in self._instances.items()}

    def _validate_call(self, parsed: ParsedCall) -> FailureKind | None:
        if parsed.function_name not in self._available_functions:
            return FailureKind.WRONG_TOOL
        if parsed.function_name not in self._methods:
            return FailureKind.WRONG_TOOL
        return None


def _invoke(method: Callable[..., object], parsed: ParsedCall) -> str:
    with blocked_side_effects():
        try:
            result = method(*parsed.args, **parsed.kwargs)
        except (ArithmeticError, AttributeError, KeyError, TypeError, ValueError) as error:
            result = f"Error during execution: {error}"
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        try:
            return json.dumps(result)
        except TypeError:
            return str(result)
    return str(result)


def _available_functions(item: Mapping[str, JsonValue]) -> set[str]:
    functions = item.get("function")
    if not isinstance(functions, list):
        return set()
    return {str(doc["name"]) for doc in functions if isinstance(doc, dict) and isinstance(doc.get("name"), str)}


def _category(item: Mapping[str, JsonValue]) -> str:
    value = item.get("category")
    return value if isinstance(value, str) else ""


def _str_list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _jsonify_public(instance: object) -> JsonValue:
    return {key: _stable_json(value) for key, value in vars(instance).items() if not key.startswith("_")}


def _stable_json(value: object) -> JsonValue:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, list | tuple | set):
        return [_stable_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _stable_json(item) for key, item in value.items()}
    if hasattr(value, "__dict__"):
        return {
            key: _stable_json(item)
            for key, item in vars(value).items()
            if not key.startswith("_") and key != "parent"
        }
    return repr(value)


def _contains_all(values: list[str], required: list[str]) -> bool:
    counts = Counter(values)
    for item in required:
        if counts[item] <= 0:
            return False
        counts[item] -= 1
    return True


def _details(env: _ExecutionEnv, responses_by_turn: list[list[str]]) -> JsonObject:
    return {"responses_by_turn": responses_by_turn, "final_state": env.state()}


def _timed_out(started: float, timeout_seconds: float) -> bool:
    return time.perf_counter() - started > timeout_seconds

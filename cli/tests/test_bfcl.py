from __future__ import annotations

import importlib
import json
import sys
import types
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final, TypeAlias

import pytest

from localbench.scorers.bfcl import build_bfcl_prompt, score_bfcl
from localbench.scorers.bfcl._parser import decode_bfcl_response

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
ReferenceScore: TypeAlias = Callable[[Mapping[str, JsonValue], str], bool]

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
_ITEM_FILE: Final = _REPO_ROOT / "suite" / "v1" / "bfcl.jsonl"
_REF_ROOT: Final = Path(__file__).resolve().parents[1] / ".venv" / "bfcl-eval-ref"
_BFCL_EVAL_ROOT: Final = _REF_ROOT / "berkeley-function-call-leaderboard"


def test_build_bfcl_prompt_when_given_item_uses_bfcl_prompting_format() -> None:
    # Given a BFCL-style prompt item with one tool.
    item = _fixture_item("simple", [{"calculate_area": {"base": [10], "height": [5], "unit": [""]}}])

    # When building the plain-chat prompt.
    prompt = build_bfcl_prompt(item)

    # Then it contains the BFCL prompting instructions, tool schemas, and user query.
    assert "You are an expert in composing functions." in prompt
    assert "[func_name1(params_name1=params_value1" in prompt
    assert "calculate_area" in prompt
    assert "Find the area of a triangle." in prompt


@pytest.mark.parametrize(
    ("category", "possible_answer", "correct_response", "wrong_response"),
    [
        (
            "simple",
            [{"calculate_area": {"base": [10], "height": [5], "unit": ["", "cm"]}}],
            "calculate_area(base=10, height=5)",
            "calculate_area(base=10, height=6)",
        ),
        (
            "multiple",
            [{"lookup_weather": {"city": ["Paris"], "unit": ["", "celsius"]}}],
            "lookup_weather(city='Paris')",
            "lookup_flights(city='Paris')",
        ),
        (
            "parallel",
            [
                {"play_song": {"artist": ["Taylor Swift"], "duration": [20]}},
                {"play_song": {"artist": ["Maroon 5"], "duration": [15]}},
            ],
            "[play_song(artist='Maroon 5', duration=15), play_song(artist='Taylor Swift', duration=20)]",
            "play_song(artist='Taylor Swift', duration=20)",
        ),
        (
            "parallel_multiple",
            [
                {"sum_values": {"values": [[3, 5]], "limit": [1000]}},
                {"multiply_primes": {"count": [5]}},
            ],
            "[multiply_primes(count=5), sum_values(values=[3, 5], limit=1000)]",
            "[multiply_primes(count=6), sum_values(values=[3, 5], limit=1000)]",
        ),
    ],
)
def test_score_bfcl_when_category_call_is_correct_or_wrong(
    category: str,
    possible_answer: list[JsonObject],
    correct_response: str,
    wrong_response: str,
) -> None:
    # Given a BFCL item for one AST category.
    item = _fixture_item(category, possible_answer)

    # When scoring correct and incorrect model responses.
    correct = score_bfcl(item, correct_response)
    wrong = score_bfcl(item, wrong_response)

    # Then the scorer returns never-raise detailed correctness.
    assert correct["correct"] is True
    assert isinstance(correct["extracted"], str)
    assert wrong == {"correct": False, "extracted": wrong["extracted"]}


def test_score_bfcl_when_output_is_malformed_never_raises() -> None:
    # Given malformed item and response shapes.
    item = _fixture_item("simple", [{"calculate_area": {"base": [10], "height": [5]}}])

    # When scoring malformed output and malformed prompt items.
    bad_output = score_bfcl(item, "not a function call")
    bad_item = score_bfcl({"id": "bad"}, "calculate_area(base=10, height=5)")

    # Then public scoring reports failure instead of raising.
    assert bad_output == {"correct": False, "extracted": None}
    assert bad_item == {"correct": False, "extracted": None}


def test_decode_bfcl_response_when_wrapped_in_language_labelled_fence() -> None:
    # Given a tool-call list wrapped in a ```python fenced code block.
    decoded = decode_bfcl_response("```python\n[add(x=1, y=2)]\n```")

    # Then the language label is stripped and the call parses (exact-AST match still gates).
    assert decoded == [{"add": {"x": 1, "y": 2}}]


def test_score_bfcl_has_live_reference_parity_when_using_pinned_bfcl_eval_ast_checker() -> None:
    # Given the pinned official BFCL evaluator checkout and a stratified sample.
    reference_score = _load_reference_score()
    items = _load_jsonl(_ITEM_FILE)
    sample = _sample_by_category(items, per_category=5)

    # When local and official AST checkers score correct and incorrect responses.
    divergences: list[str] = []
    for item in sample:
        for label, response in [("expected", _expected_response(item)), ("wrong", "definitely_not_a_function()")]:
            local = score_bfcl(item, response)["correct"]
            reference = reference_score(item, response)
            if local is not reference:
                divergences.append(f"{item['id']} {label}: local={local} reference={reference}")

    # Then verdicts match exactly.
    assert divergences == []
    assert len(sample) == 20


def _fixture_item(category: str, possible_answer: list[JsonObject]) -> JsonObject:
    functions = [_function_schema(function_name, params) for answer in possible_answer for function_name, params in answer.items()]
    return {
        "id": "bfcl-test-001",
        "source_id": f"{category}_fixture",
        "category": category,
        "question": [[{"role": "user", "content": "Find the area of a triangle."}]],
        "function": functions,
        "possible_answer": possible_answer,
    }


def _function_schema(function_name: str, params: Mapping[str, JsonValue]) -> JsonObject:
    properties = {
        key: {"type": _schema_type(values), "description": key}
        for key, values in params.items()
        if isinstance(values, list)
    }
    required = [key for key, values in params.items() if isinstance(values, list) and "" not in values]
    return {
        "name": function_name,
        "description": f"Tool {function_name}.",
        "parameters": {"type": "dict", "properties": properties, "required": required},
    }


def _schema_type(values: JsonValue) -> str:
    candidates = values if isinstance(values, list) else []
    first = next((value for value in candidates if value != ""), "")
    if isinstance(first, bool):
        return "boolean"
    if isinstance(first, int):
        return "integer"
    if isinstance(first, float):
        return "float"
    if isinstance(first, list):
        return "array"
    if isinstance(first, dict):
        return "dict"
    return "string"


def _load_reference_score() -> ReferenceScore:
    if not _BFCL_EVAL_ROOT.exists():
        pytest.fail(f"Missing pinned bfcl-eval checkout at {_REF_ROOT}. Clone ShishirPatil/gorilla@6ea57973c7a6097fd7c5915698c54c17c5b1b6c8 there.")
    original_path = list(sys.path)
    sys.path.insert(0, str(_BFCL_EVAL_ROOT))
    model_config = types.ModuleType("bfcl_eval.constants.model_config")
    model_config.MODEL_CONFIG_MAPPING = {"gorilla-openfunctions-v2": types.SimpleNamespace(underscore_to_dot=False)}
    sys.modules["bfcl_eval.constants.model_config"] = model_config
    try:
        enums = importlib.import_module("bfcl_eval.constants.enums")
        checker = importlib.import_module("bfcl_eval.eval_checker.ast_eval.ast_checker")
    finally:
        sys.path = original_path

    def _score(prompt_item: Mapping[str, JsonValue], response_text: str) -> bool:
        decoded = decode_bfcl_response(response_text)
        if decoded is None:
            return False
        result = checker.ast_checker(
            prompt_item["function"],
            decoded,
            prompt_item["possible_answer"],
            enums.Language.PYTHON,
            str(prompt_item["category"]),
            "gorilla-openfunctions-v2",
        )
        return bool(result["valid"])

    return _score


def _load_jsonl(path: Path) -> list[JsonObject]:
    rows: list[JsonObject] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise AssertionError(f"{path.name} contains a non-object row")
            rows.append(parsed)
    return rows


def _sample_by_category(items: list[JsonObject], per_category: int) -> list[JsonObject]:
    sample: list[JsonObject] = []
    for category in ["simple", "multiple", "parallel", "parallel_multiple"]:
        selected = [item for item in items if item.get("category") == category][:per_category]
        sample.extend(selected)
    return sample


def _expected_response(item: Mapping[str, JsonValue]) -> str:
    possible_answer = item["possible_answer"]
    if not isinstance(possible_answer, list):
        raise AssertionError(f"{item['id']}: possible_answer must be a list")
    required_by_function = _required_by_function(item)
    calls = [_call_text(call, required_by_function) for call in possible_answer if isinstance(call, dict)]
    return "[" + ", ".join(calls) + "]"


def _required_by_function(item: Mapping[str, JsonValue]) -> dict[str, set[str]]:
    functions = item["function"]
    if not isinstance(functions, list):
        return {}
    required: dict[str, set[str]] = {}
    for function in functions:
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        parameters = function.get("parameters")
        if not isinstance(name, str) or not isinstance(parameters, dict):
            continue
        required_params = parameters.get("required")
        if isinstance(required_params, list):
            required[name] = {param for param in required_params if isinstance(param, str)}
    return required


def _call_text(call: Mapping[str, JsonValue], required_by_function: Mapping[str, set[str]]) -> str:
    function_name, params = next(iter(call.items()))
    if not isinstance(params, dict):
        raise AssertionError(f"{function_name}: params must be an object")
    required = required_by_function.get(function_name, set())
    args = [
        f"{key}={_repr_value(values)}"
        for key, values in params.items()
        if isinstance(values, list) and (key in required or "" not in values)
    ]
    return f"{function_name}(" + ", ".join(args) + ")"


def _repr_value(values: list[JsonValue]) -> str:
    value = next(item for item in values if item != "")
    return repr(_materialize(value))


def _materialize(value: JsonValue) -> JsonValue:
    if isinstance(value, list):
        return [_materialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _materialize_list(item) if isinstance(item, list) else _materialize(item) for key, item in value.items()}
    return value


def _materialize_list(values: list[JsonValue]) -> JsonValue:
    value = next(item for item in values if item != "")
    return _materialize(value)

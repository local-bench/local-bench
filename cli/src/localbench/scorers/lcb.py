"""LiveCodeBench Test Output Prediction scorer (exec-free)."""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Mapping
from typing import Final, TypeAlias, TypedDict

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class LCBScore(TypedDict):
    correct: bool
    extracted: str | None


_DEFAULT_TEMPLATE: Final = (
    "You are a helpful programming assistant and an expert Python programmer.\n"
    "Predict the output for the provided LiveCodeBench test case. Do not run code.\n\n"
    "Problem:\n{question_content}\n\n"
    "Function:\n```\n{starter_code}\n```\n\n"
    "Test input:\n```\n{test_input}\n```\n\n"
    "Only return the predicted output."
)
_FENCE_RE: Final = re.compile(r"```(?:python|Python)?\s*\n(?P<body>.*?)```", re.DOTALL)


def build_lcb_prompt(prompt_item: Mapping[str, JsonValue], template: str | None = None) -> str:
    question_content = _string(prompt_item.get("question_content"))
    starter_code = _string(prompt_item.get("starter_code"))
    test_input = _string(prompt_item.get("input"))
    if question_content is None or starter_code is None or test_input is None:
        return ""
    prompt_template = template if template is not None else _DEFAULT_TEMPLATE
    return prompt_template.format(
        question_content=question_content,
        starter_code=starter_code,
        test_input=test_input,
    )


def score_lcb(prompt_item: Mapping[str, JsonValue], response_text: str) -> LCBScore:
    expected_text = _string(prompt_item.get("answer"))
    if expected_text is None:
        return {"correct": False, "extracted": None}
    expected = _parse_json_value(expected_text)
    predicted = _parse_response_value(response_text)
    if predicted is None and isinstance(expected, str):
        # An unquoted string output ("hello") fails literal/JSON parsing but is a valid answer
        # when it exactly equals the string gold. Compare the candidate verbatim — a genuinely
        # quoted string already parses via literal_eval, so this only catches the bare case and
        # cannot credit quote/backtick-wrapped text that differs from the gold.
        bare = _candidate_text(response_text).strip()
        if bare == expected:
            return {"correct": True, "extracted": _canonical(expected)}
    if expected is None or predicted is None:
        return {"correct": False, "extracted": None}
    extracted = _canonical(predicted)
    return {"correct": predicted == expected, "extracted": extracted}


def _parse_response_value(response_text: str) -> JsonValue | None:
    candidate = _candidate_text(response_text)
    if not candidate:
        return None
    assertion_output = _assertion_output(candidate)
    if assertion_output is not None:
        candidate = assertion_output
    return _parse_literal_value(candidate)


def _candidate_text(response_text: str) -> str:
    stripped = response_text.strip()
    if not stripped:
        return ""
    assert_lines = [
        line.strip()
        for line in stripped.splitlines()
        if line.strip().startswith("assert")
    ]
    if assert_lines:
        return assert_lines[-1]
    match = _FENCE_RE.search(stripped)
    if match is not None:
        body = match.group("body").strip()
        nested_assert_lines = [
            line.strip()
            for line in body.splitlines()
            if line.strip().startswith("assert")
        ]
        return nested_assert_lines[-1] if nested_assert_lines else body
    return stripped


def _assertion_output(candidate: str) -> str | None:
    try:
        parsed = ast.parse(candidate, mode="exec")
    except SyntaxError:
        return None
    if not parsed.body or not isinstance(parsed.body[0], ast.Assert):
        return None
    comparison = parsed.body[0].test
    if (
        not isinstance(comparison, ast.Compare)
        or len(comparison.ops) != 1
        or not isinstance(comparison.ops[0], ast.Eq)
        or len(comparison.comparators) != 1
    ):
        return None
    return ast.get_source_segment(candidate, comparison.comparators[0])


def _parse_json_value(value: str) -> JsonValue | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if _is_json_value(parsed) else None


def _parse_literal_value(value: str) -> JsonValue | None:
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return _parse_json_value(value)
    return _tuple_to_list(parsed) if _is_literal_value(parsed) else None


def _is_json_value(value: JsonValue) -> bool:
    return isinstance(value, str | int | float | bool) or value is None or _is_json_container(value)


def _is_json_container(value: JsonValue) -> bool:
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    return False


def _is_literal_value(value: object) -> bool:
    if isinstance(value, str | int | float | bool) or value is None:
        return True
    if isinstance(value, list | tuple):
        return all(_is_literal_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_literal_value(item) for key, item in value.items())
    return False


def _tuple_to_list(value: object) -> JsonValue:
    if isinstance(value, tuple):
        return [_tuple_to_list(item) for item in value]
    if isinstance(value, list):
        return [_tuple_to_list(item) for item in value]
    if isinstance(value, dict):
        return {key: _tuple_to_list(item) for key, item in value.items() if isinstance(key, str)}
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    raise TypeError(f"non-json literal: {type(value).__name__}")


def _canonical(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None

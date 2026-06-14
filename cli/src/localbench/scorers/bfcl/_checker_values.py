from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TypeAlias

from localbench.scorers.bfcl._types import AstValue, CheckResult, JsonValue

ExpectedType: TypeAlias = type[str] | type[int] | type[float] | type[bool] | type[list[AstValue]] | type[dict[str, AstValue]]
_PYTHON_TYPE_MAPPING: Mapping[str, ExpectedType] = {
    "string": str,
    "integer": int,
    "float": float,
    "boolean": bool,
    "array": list,
    "tuple": list,
    "dict": dict,
    "any": str,
}


def standardize_string(input_string: str) -> str:
    return re.sub(r"[ \,\.\/\-\_\*\^]", "", input_string).lower().replace("'", '"')


def get_expected_type(type_description: str) -> ExpectedType:
    return _PYTHON_TYPE_MAPPING[type_description]


def value_type_check(
    param: str,
    value: AstValue,
    possible_answer: list[JsonValue],
    expected_type_description: str,
    expected_type: ExpectedType,
    nested_type: ExpectedType | None,
) -> tuple[CheckResult, bool]:
    result = _valid()
    possible_answer_type = _possible_answer_type(possible_answer)
    is_variable = possible_answer_type is not None and possible_answer_type is not expected_type
    if type(value) is expected_type:
        if nested_type is None:
            return result, is_variable
        nested_result = _nested_type_check(param, value, possible_answer, expected_type_description, nested_type)
        return nested_result, is_variable
    if possible_answer_type is not None and type(value) is possible_answer_type:
        return result, True
    return {
        "valid": False,
        "error": [
            f"Incorrect type for parameter {param!r}. Expected type {expected_type_description}, got {type(value).__name__}. Parameter value: {value!r}."
        ],
        "error_type": "type_error:simple",
    }, False


def check_string(param: str, model_output: str, possible_answer: list[JsonValue]) -> CheckResult:
    model_value = standardize_string(model_output)
    answers = [standardize_string(item) for item in possible_answer if isinstance(item, str)]
    if model_value not in answers:
        return _invalid(f"Invalid value for parameter {param!r}: {model_output!r}. Expected one of {possible_answer}. Case insensitive.", "value_error:string")
    return _valid()


def check_list(param: str, model_output: list[AstValue], possible_answer: list[JsonValue]) -> CheckResult:
    model_value = [standardize_string(item) if isinstance(item, str) else item for item in model_output]
    answers: list[list[JsonValue]] = []
    for item in possible_answer:
        if isinstance(item, list):
            answers.append([standardize_string(value) if isinstance(value, str) else value for value in item])
    if model_value not in answers:
        return _invalid(f"Invalid value for parameter {param!r}: {model_output!r}. Expected one of {possible_answer}.", "value_error:list/tuple")
    return _valid()


def check_dict(param: str, model_output: Mapping[str, AstValue], possible_answers: list[JsonValue]) -> CheckResult:
    result = _invalid("", "dict_checker:unclear")
    for possible_answer in possible_answers:
        if possible_answer == "":
            continue
        if not isinstance(possible_answer, dict):
            continue
        result = _check_dict_candidate(model_output, possible_answer)
        if result["valid"]:
            return result
    if not result["error"]:
        return _invalid(f"Invalid dictionary for parameter {param!r}.", "dict_checker:unclear")
    return result


def check_list_dict(param: str, model_output: list[AstValue], possible_answers: list[JsonValue]) -> CheckResult:
    result = _invalid("", "list_dict_checker:unclear")
    for answer in possible_answers:
        if not isinstance(answer, list):
            continue
        if len(model_output) != len(answer):
            result = _invalid("Wrong number of dictionaries in the list.", "value_error:list_dict_count")
            continue
        for model_item, answer_item in zip(model_output, answer, strict=True):
            if not isinstance(model_item, dict) or not isinstance(answer_item, dict):
                result = _invalid("List item is not a dictionary.", "value_error:list_dict_type")
                break
            result = check_dict(param, model_item, [answer_item])
            if not result["valid"]:
                break
        if result["valid"]:
            return result
    return result


def _possible_answer_type(possible_answer: list[JsonValue]) -> type[JsonValue] | None:
    for answer in possible_answer:
        if answer != "":
            return type(answer)
    return None


def _nested_type_check(
    param: str,
    value: AstValue,
    possible_answer: list[JsonValue],
    expected_type_description: str,
    nested_type: ExpectedType,
) -> CheckResult:
    if not isinstance(value, list):
        return _invalid(f"Nested type checking failed for parameter {param!r}.", "type_error:nested")
    for possible_answer_item in possible_answer:
        if isinstance(possible_answer_item, list) and all(type(value_item) is nested_type for value_item in value):
            return _valid()
    return _invalid(
        f"Nested type checking failed for parameter {param!r}. Expected outer type {expected_type_description} with inner type {nested_type}. Parameter value: {value!r}.",
        "type_error:nested",
    )


def _check_dict_candidate(model_output: Mapping[str, AstValue], possible_answer: Mapping[str, JsonValue]) -> CheckResult:
    for key, value in model_output.items():
        if key not in possible_answer:
            return _invalid(f"Unexpected dict key parameter: '{key}'.", "value_error:dict_key")
        answers = possible_answer[key]
        if not isinstance(answers, list):
            return _invalid(f"Invalid possible answer for dict key parameter: '{key}'.", "value_error:dict_value")
        candidate = standardize_string(value) if isinstance(value, str) else value
        possible_values = [standardize_string(item) if isinstance(item, str) else item for item in answers]
        if candidate not in possible_values:
            return _invalid(f"Invalid value for parameter {key!r}: {value!r}. Expected one of {possible_values}.", "value_error:dict_value")
    for key, value in possible_answer.items():
        if key not in model_output and isinstance(value, list) and "" not in value:
            return _invalid(f"Missing dict key parameter: '{key}'.", "value_error:dict_key")
    return _valid()


def _valid() -> CheckResult:
    return {"valid": True, "error": [], "error_type": ""}


def _invalid(message: str, error_type: str) -> CheckResult:
    return {"valid": False, "error": [message] if message else [], "error_type": error_type}

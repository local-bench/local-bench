from __future__ import annotations

from collections.abc import Mapping

from localbench.scorers.bfcl._checker_values import (
    check_dict,
    check_list,
    check_list_dict,
    check_string,
    get_expected_type,
    value_type_check,
)
from localbench.scorers.bfcl._types import AstCall, AstValue, CheckResult, JsonObject, JsonValue


def check_bfcl_call(
    function_docs: list[JsonObject],
    model_output: list[AstCall],
    possible_answer: list[JsonObject],
    category: str,
) -> CheckResult:
    if "parallel" in category:
        return _parallel_function_checker(function_docs, model_output, possible_answer)
    if "multiple" in category:
        return _multiple_function_checker(function_docs, model_output, possible_answer)
    if len(model_output) != 1:
        return _invalid("Wrong number of functions.", "simple_function_checker:wrong_count")
    return _simple_function_checker(function_docs[0], model_output[0], possible_answer[0])


def _find_description(function_docs: list[JsonObject], name: str) -> JsonObject | None:
    for function_doc in function_docs:
        if function_doc.get("name") == name:
            return function_doc
    return None


def _simple_function_checker(function_doc: JsonObject, model_output: AstCall, possible_answer: JsonObject) -> CheckResult:
    answer_name, answer_params = _single_possible_answer(possible_answer)
    function_name = _string(function_doc.get("name"))
    if function_name is None or answer_name != function_name:
        return _invalid(f"Function name {function_name!r} not found in model output.", "simple_function_checker:wrong_func_name")
    model_params = model_output.get(function_name)
    if model_params is None:
        return _invalid(f"Function name {function_name!r} not found in model output.", "simple_function_checker:wrong_func_name")
    parameters = function_doc.get("parameters")
    if not isinstance(parameters, dict):
        return _invalid("Function parameters are malformed.", "simple_function_checker:malformed_function")
    properties = parameters.get("properties")
    required_params = parameters.get("required")
    if not isinstance(properties, dict) or not isinstance(required_params, list):
        return _invalid("Function parameter schema is malformed.", "simple_function_checker:malformed_function")
    for param in required_params:
        if isinstance(param, str) and param not in model_params:
            return _invalid(f"Missing required parameter: {param!r}.", "simple_function_checker:missing_required")
    for param, value in model_params.items():
        param_result = _check_param(param, value, properties, answer_params)
        if not param_result["valid"]:
            return param_result
    for param, values in answer_params.items():
        if param not in model_params and "" not in values:
            return _invalid(f"Optional parameter {param!r} not provided and not marked as optional.", "simple_function_checker:missing_optional")
    return _valid()


def _check_param(
    param: str,
    value: AstValue,
    properties: Mapping[str, JsonValue],
    possible_answer: Mapping[str, list[JsonValue]],
) -> CheckResult:
    if param not in properties or param not in possible_answer:
        return _invalid(f"Unexpected parameter: {param!r}.", "simple_function_checker:unexpected_param")
    full_param_details = properties[param]
    if not isinstance(full_param_details, dict):
        return _invalid(f"Parameter schema is malformed: {param!r}.", "simple_function_checker:malformed_function")
    expected_type_description = _string(full_param_details.get("type"))
    if expected_type_description is None:
        return _invalid(f"Parameter type is missing: {param!r}.", "simple_function_checker:malformed_function")
    expected_type = get_expected_type(expected_type_description)
    nested_type = _nested_type(full_param_details, expected_type_description)
    if expected_type_description == "tuple" and isinstance(value, tuple):
        value = list(value)
    if expected_type_description == "float" and type(value) is int:
        value = float(value)
    type_result, is_variable = value_type_check(param, value, possible_answer[param], expected_type_description, expected_type, nested_type)
    if not type_result["valid"]:
        return type_result
    if not is_variable:
        special = _check_special_value(param, value, expected_type, nested_type, possible_answer[param])
        if special is not None:
            return special
    if value not in possible_answer[param]:
        return _invalid(f"Invalid value for parameter {param!r}: {value!r}. Expected one of {possible_answer[param]}.", "value_error:others")
    return _valid()


def _check_special_value(
    param: str,
    value: AstValue,
    expected_type: type,
    nested_type: type | None,
    possible_answer: list[JsonValue],
) -> CheckResult | None:
    if expected_type is dict and isinstance(value, dict):
        return check_dict(param, value, possible_answer)
    if expected_type is list and nested_type is dict and isinstance(value, list):
        return check_list_dict(param, value, possible_answer)
    if expected_type is str and isinstance(value, str):
        return check_string(param, value, possible_answer)
    if expected_type is list and isinstance(value, list):
        return check_list(param, value, possible_answer)
    return None


def _nested_type(param_details: Mapping[str, JsonValue], expected_type_description: str) -> type | None:
    if expected_type_description not in {"array", "tuple"}:
        return None
    items = param_details.get("items")
    if not isinstance(items, dict):
        return None
    nested = items.get("type")
    if not isinstance(nested, str):
        return None
    return get_expected_type(nested)


def _parallel_function_checker(function_docs: list[JsonObject], model_output: list[AstCall], possible_answers: list[JsonObject]) -> CheckResult:
    if len(model_output) != len(possible_answers):
        return _invalid("Wrong number of functions.", "parallel_function_checker_no_order:wrong_count")
    matched_indices: set[int] = set()
    for index, possible_answer in enumerate(possible_answers):
        expected_name = next(iter(possible_answer))
        function_doc = _find_description(function_docs, expected_name)
        if function_doc is None:
            return _invalid(f"Function description not found for {expected_name!r}.", "parallel_function_checker_no_order:missing_function")
        matched = _match_any(function_doc, model_output, possible_answer, matched_indices)
        if matched is None:
            return _invalid(f"Could not find a matching function for index {index} of possible answers.", "parallel_function_checker_no_order:cannot_find_match")
        matched_indices.add(matched)
    return _valid()


def _multiple_function_checker(function_docs: list[JsonObject], model_output: list[AstCall], possible_answers: list[JsonObject]) -> CheckResult:
    if len(model_output) != len(possible_answers):
        return _invalid("Wrong number of functions.", "multiple_function_checker:wrong_count")
    expected_name = next(iter(possible_answers[0]))
    function_doc = _find_description(function_docs, expected_name)
    if function_doc is None:
        return _invalid(f"Function description not found for {expected_name!r}.", "multiple_function_checker:missing_function")
    return _simple_function_checker(function_doc, model_output[0], possible_answers[0])


def _match_any(function_doc: JsonObject, model_output: list[AstCall], possible_answer: JsonObject, matched_indices: set[int]) -> int | None:
    for index, model_call in enumerate(model_output):
        if index in matched_indices:
            continue
        if _simple_function_checker(function_doc, model_call, possible_answer)["valid"]:
            return index
    return None


def _single_possible_answer(possible_answer: JsonObject) -> tuple[str, dict[str, list[JsonValue]]]:
    function_name = next(iter(possible_answer))
    params = possible_answer[function_name]
    if not isinstance(params, dict):
        raise TypeError("possible answer parameters must be an object")
    return function_name, {key: value for key, value in params.items() if isinstance(value, list)}


def _string(value: JsonValue) -> str | None:
    return value if isinstance(value, str) else None


def _valid() -> CheckResult:
    return {"valid": True, "error": [], "error_type": ""}


def _invalid(message: str, error_type: str) -> CheckResult:
    return {"valid": False, "error": [message], "error_type": error_type}

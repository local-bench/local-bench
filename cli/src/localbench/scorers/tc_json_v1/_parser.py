from __future__ import annotations

import json
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from typing import Final

from localbench.scorers._reasoning import strip_reasoning
from localbench.scorers.tc_json_v1._types import (
    FailureDiagnostics,
    JsonObject,
    JsonValue,
    MatchPolicy,
    ParseResult,
    ToolCall,
    ToolSpec,
    ValidationResult,
)

SCHEMA_VERSION: Final = "localbench.tc.v1"
TOOL_NAME_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
WRAPPING_JSON_FENCE_RE: Final = re.compile(
    r"```(?:json)?[ \t]*\r?\n(?P<json>.*)\r?\n```",
    flags=re.DOTALL | re.IGNORECASE,
)


def parse_single_json_object(response_text: str) -> ParseResult:
    stripped = strip_reasoning(response_text).strip()
    fenced = WRAPPING_JSON_FENCE_RE.fullmatch(stripped)
    if fenced is not None:
        stripped = fenced.group("json").strip()
    if not stripped:
        return {"value": None, "extracted": None, "failure_reason": "invalid_json"}
    decoder = json.JSONDecoder()
    try:
        parsed, end = decoder.raw_decode(stripped)
    except json.JSONDecodeError:
        return {"value": None, "extracted": None, "failure_reason": "invalid_json"}
    if stripped[end:].strip():
        return {
            "value": None,
            "extracted": None,
            "failure_reason": "extra_text_or_multiple_json_objects",
        }
    if not isinstance(parsed, dict):
        return {"value": None, "extracted": None, "failure_reason": "invalid_json"}
    extracted = json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"value": parsed, "extracted": extracted, "failure_reason": None}


def validate_response_schema(value: Mapping[str, JsonValue]) -> ValidationResult:
    if set(value) - {"schema_version", "calls"}:
        return {"valid": False, "message": "response has additional properties"}
    if "schema_version" not in value or "calls" not in value:
        return {"valid": False, "message": "response missing required properties"}
    if not isinstance(value["schema_version"], str):
        return {"valid": False, "message": "schema_version must be a string"}
    calls = value["calls"]
    if not isinstance(calls, list) or len(calls) > 8:
        return {"valid": False, "message": "calls must be an array with at most 8 items"}
    for call in calls:
        if not isinstance(call, dict):
            return {"valid": False, "message": "call must be an object"}
        if set(call) != {"name", "arguments"}:
            return {"valid": False, "message": "call must contain only name and arguments"}
        name = call["name"]
        arguments = call["arguments"]
        if not isinstance(name, str) or TOOL_NAME_RE.fullmatch(name) is None:
            return {"valid": False, "message": "call name is invalid"}
        if not isinstance(arguments, dict):
            return {"valid": False, "message": "call arguments must be an object"}
    return {"valid": True}


def validate_arguments(
    arguments: Mapping[str, JsonValue],
    schema: Mapping[str, JsonValue],
    normalizers: Mapping[str, str] | None = None,
) -> ValidationResult:
    return _validate_value(dict(arguments), schema, "", normalizers or {})


def calls_match(
    predicted: list[ToolCall],
    gold: list[ToolCall],
    tools: Mapping[str, ToolSpec],
    policy: MatchPolicy,
    *,
    order_matters: bool,
) -> tuple[bool, FailureDiagnostics]:
    diagnostics = _empty_diagnostics()
    if order_matters:
        for predicted_call, gold_call in zip(predicted, gold, strict=True):
            if not _single_call_matches(predicted_call, gold_call, tools, policy):
                diagnostics["arg_mismatch"].append(
                    {"predicted": predicted_call, "gold": gold_call}
                )
        return not diagnostics["arg_mismatch"], diagnostics

    unmatched_predicted = set(range(len(predicted)))
    for gold_call in gold:
        match_index = None
        for index in sorted(unmatched_predicted):
            if _single_call_matches(predicted[index], gold_call, tools, policy):
                match_index = index
                break
        if match_index is None:
            diagnostics["missing_call"].append(gold_call)
        else:
            unmatched_predicted.remove(match_index)
    diagnostics["extra_call"] = [predicted[index] for index in sorted(unmatched_predicted)]
    if diagnostics["missing_call"] or diagnostics["extra_call"]:
        diagnostics["arg_mismatch"].append({"predicted": predicted, "gold": gold})
    return not (
        diagnostics["missing_call"]
        or diagnostics["extra_call"]
        or diagnostics["arg_mismatch"]
    ), diagnostics


def _single_call_matches(
    predicted: ToolCall,
    gold: ToolCall,
    tools: Mapping[str, ToolSpec],
    policy: MatchPolicy,
) -> bool:
    if predicted["name"] != gold["name"]:
        return False
    tool = tools.get(gold["name"])
    if tool is None:
        return False
    predicted_args = _with_defaults(predicted["arguments"], tool["parameters"], policy)
    gold_args = _with_defaults(gold["arguments"], tool["parameters"], policy)
    return _canonical_equal(predicted_args, gold_args, "", policy)


def _with_defaults(
    arguments: Mapping[str, JsonValue],
    schema: Mapping[str, JsonValue],
    policy: MatchPolicy,
) -> JsonObject:
    output = dict(arguments)
    if not policy["allow_default_omission"]:
        return output
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return output
    for key, property_schema in properties.items():
        if key in output or not isinstance(key, str) or not isinstance(property_schema, dict):
            continue
        if "default" in property_schema:
            output[key] = property_schema["default"]
    return output


def _canonical_equal(left: JsonValue, right: JsonValue, pointer: str, policy: MatchPolicy) -> bool:
    left = _normalize_value(left, pointer, policy)
    right = _normalize_value(right, pointer, policy)
    if _is_number(left) and _is_number(right):
        return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=0.0)
    if isinstance(left, str) and isinstance(right, str):
        return left == right
    if isinstance(left, dict) and isinstance(right, dict):
        if set(left) != set(right):
            return False
        return all(
            _canonical_equal(left[key], right[key], _join_pointer(pointer, key), policy)
            for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return False
        if pointer in set(policy["unordered_arrays"]):
            unmatched = list(range(len(right)))
            for left_item in left:
                matched = next(
                    (
                        index
                        for index in unmatched
                        if _canonical_equal(left_item, right[index], pointer + "/*", policy)
                    ),
                    None,
                )
                if matched is None:
                    return False
                unmatched.remove(matched)
            return True
        return all(
            _canonical_equal(left_item, right_item, f"{pointer}/{index}", policy)
            for index, (left_item, right_item) in enumerate(zip(left, right, strict=True))
        )
    return left == right


def _normalize_value(value: JsonValue, pointer: str, policy: MatchPolicy) -> JsonValue:
    if not isinstance(value, str):
        return value
    normalized = unicodedata.normalize("NFC", value)
    normalizer = policy["normalizers"].get(pointer)
    match normalizer:
        case None:
            return normalized
        case "iso_date":
            return _normalize_iso_date(normalized)
        case "iso_datetime":
            return _normalize_iso_datetime(normalized)
        case "hhmm_24h":
            return _normalize_hhmm(normalized)
        case "enum-casefold":
            return normalized.casefold()
        case _:
            # Fail closed: an unknown / mistyped normalizer id must NOT fall through to
            # an implicit None (which would collapse BOTH gold and predicted to None and
            # accept any value — a silent false-pass the gold-self-score gate cannot catch).
            # Fall back to a plain NFC string compare so a misdeclared normalizer is, at
            # worst, a no-op — never an accept-anything.
            return normalized


def _normalize_iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return value


def _normalize_iso_datetime(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return value


def _normalize_hhmm(value: str) -> str:
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return time.fromisoformat(value).strftime("%H:%M")
        except ValueError:
            continue
    return value


def _validate_value(
    value: JsonValue,
    schema: Mapping[str, JsonValue],
    pointer: str,
    normalizers: Mapping[str, str],
) -> ValidationResult:
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        if any(_validate_type(value, item) for item in schema_type if isinstance(item, str)):
            return _validate_constraints(value, schema, pointer, normalizers)
        return {"valid": False, "message": f"{pointer or '/'} has invalid type"}
    if isinstance(schema_type, str) and not _validate_type(value, schema_type):
        return {"valid": False, "message": f"{pointer or '/'} has invalid type"}
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        if normalizers.get(pointer) == "enum-casefold" and isinstance(value, str):
            folded = {item.casefold() for item in enum if isinstance(item, str)}
            if value.casefold() in folded:
                return _validate_constraints(value, schema, pointer, normalizers)
        return {"valid": False, "message": f"{pointer or '/'} is not an allowed enum value"}
    const = schema.get("const")
    if "const" in schema and value != const:
        return {"valid": False, "message": f"{pointer or '/'} does not match const"}
    return _validate_constraints(value, schema, pointer, normalizers)


def _validate_constraints(
    value: JsonValue,
    schema: Mapping[str, JsonValue],
    pointer: str,
    normalizers: Mapping[str, str],
) -> ValidationResult:
    if isinstance(value, dict):
        required = schema.get("required")
        if isinstance(required, list):
            missing = [item for item in required if isinstance(item, str) and item not in value]
            if missing:
                return {"valid": False, "message": f"{pointer or '/'} missing {missing[0]}"}
        properties = schema.get("properties")
        property_map = properties if isinstance(properties, dict) else {}
        additional = schema.get("additionalProperties", True)
        if additional is False:
            extras = set(value) - {key for key in property_map if isinstance(key, str)}
            if extras:
                return {"valid": False, "message": f"{pointer or '/'} has extra property"}
        for key, item in value.items():
            child_schema = property_map.get(key)
            if isinstance(child_schema, dict):
                result = _validate_value(item, child_schema, _join_pointer(pointer, key), normalizers)
                if not result["valid"]:
                    return result
    if isinstance(value, list):
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if isinstance(min_items, int) and len(value) < min_items:
            return {"valid": False, "message": f"{pointer or '/'} has too few items"}
        if isinstance(max_items, int) and len(value) > max_items:
            return {"valid": False, "message": f"{pointer or '/'} has too many items"}
        items = schema.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(value):
                result = _validate_value(item, items, f"{pointer}/{index}", normalizers)
                if not result["valid"]:
                    return result
    return {"valid": True}


def _validate_type(value: JsonValue, schema_type: str) -> bool:
    match schema_type:
        case "object":
            return isinstance(value, dict)
        case "array":
            return isinstance(value, list)
        case "string":
            return isinstance(value, str)
        case "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        case "number":
            return _is_number(value)
        case "boolean":
            return isinstance(value, bool)
        case "null":
            return value is None
        case _:
            return True


def _is_number(value: JsonValue) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _join_pointer(parent: str, key: str) -> str:
    escaped = key.replace("~", "~0").replace("/", "~1")
    return f"{parent}/{escaped}" if parent else f"/{escaped}"


def _empty_diagnostics() -> FailureDiagnostics:
    return {"extra_call": [], "missing_call": [], "arg_mismatch": []}


def response_calls(value: Mapping[str, JsonValue]) -> list[ToolCall]:
    calls = value["calls"]
    if not isinstance(calls, list):
        return []
    output: list[ToolCall] = []
    for call in calls:
        if isinstance(call, dict) and isinstance(call.get("name"), str) and isinstance(call.get("arguments"), dict):
            output.append({"name": call["name"], "arguments": call["arguments"]})
    return output


def tool_map(tools: Sequence[ToolSpec]) -> dict[str, ToolSpec]:
    return {tool["name"]: tool for tool in tools}

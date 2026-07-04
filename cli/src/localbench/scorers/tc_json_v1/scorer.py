from __future__ import annotations

import json
from collections.abc import Mapping

from localbench.scorers.tc_json_v1._parser import (
    SCHEMA_VERSION,
    calls_match,
    parse_single_json_object,
    response_calls,
    tool_map,
    validate_arguments,
    validate_response_schema,
)
from localbench.scorers.tc_json_v1._types import (
    FailureDiagnostics,
    JsonValue,
    TCJsonItem,
    TCJsonScore,
    ToolCall,
    ToolSpec,
)

tc_json_v1_scorer = 1


def score_tc_json_v1(prompt_item: Mapping[str, JsonValue], response_text: str) -> TCJsonScore:
    try:  # noqa: BROAD_EXCEPT_OK - public scorer contract requires failure results.
        item = _coerce_item(prompt_item)
        if item is None:
            return _failure("response_schema_invalid", None, None)
        parsed = parse_single_json_object(response_text if isinstance(response_text, str) else "")
        if parsed["failure_reason"] is not None:
            return _failure(parsed["failure_reason"], parsed["extracted"], None)
        value = parsed["value"]
        if value is None:
            return _failure("invalid_json", parsed["extracted"], None)
        response_schema = validate_response_schema(value)
        if not response_schema["valid"]:
            return _failure("response_schema_invalid", parsed["extracted"], _schema_version(value))
        if value["schema_version"] != SCHEMA_VERSION:
            return _failure("wrong_schema_version", parsed["extracted"], _schema_version(value), schema_valid=True)
        predicted = response_calls(value)
        gold = item["gold"]["calls"]
        if len(predicted) != len(gold):
            return _failure(
                "wrong_call_count",
                parsed["extracted"],
                SCHEMA_VERSION,
                schema_valid=True,
                diagnostics=_count_diagnostics(predicted, gold),
            )
        tools = tool_map(item["tools"])
        wrong_tools = [call for call in predicted if call["name"] not in tools]
        if wrong_tools:
            return _failure(
                "wrong_tool",
                parsed["extracted"],
                SCHEMA_VERSION,
                schema_valid=True,
                diagnostics={"extra_call": wrong_tools, "missing_call": [], "arg_mismatch": []},
            )
        for call in predicted:
            result = validate_arguments(
                call["arguments"],
                tools[call["name"]]["parameters"],
                item["match_policy"]["normalizers"],
            )
            if not result["valid"]:
                return _failure(
                    "arg_schema_invalid",
                    parsed["extracted"],
                    SCHEMA_VERSION,
                    schema_valid=True,
                    diagnostics={"extra_call": [], "missing_call": [], "arg_mismatch": [call]},
                )
        matched, diagnostics = calls_match(
            predicted,
            gold,
            tools,
            item["match_policy"],
            order_matters=item["gold"]["order_matters"],
        )
        if not matched:
            return _failure(
                "call_or_arg_mismatch",
                parsed["extracted"],
                SCHEMA_VERSION,
                schema_valid=True,
                diagnostics=diagnostics,
            )
        return {
            "correct": True,
            "extracted": parsed["extracted"],
            "failure_reason": None,
            "diagnostics": _empty_diagnostics(),
            "response_schema_valid": True,
            "schema_version": SCHEMA_VERSION,
        }
    except Exception:  # noqa: BROAD_EXCEPT_OK - public scorer contract requires never raising.
        return _failure("response_schema_invalid", None, None)


def build_tc_json_prompt(prompt_item: Mapping[str, JsonValue], template: str) -> str:
    tools = prompt_item.get("tools")
    prompt = prompt_item.get("prompt")
    if not isinstance(tools, list) or not isinstance(prompt, str):
        return ""
    return template.replace(
        "{tool_catalog}",
        json.dumps(tools, ensure_ascii=False, sort_keys=True, indent=2),
    ).replace("{user_request}", prompt)


def _coerce_item(prompt_item: Mapping[str, JsonValue]) -> TCJsonItem | None:
    tools = prompt_item.get("tools")
    gold = prompt_item.get("gold")
    policy = prompt_item.get("match_policy")
    if not isinstance(tools, list) or not isinstance(gold, dict) or not isinstance(policy, dict):
        return None
    typed_tools: list[ToolSpec] = []
    for tool in tools:
        if not isinstance(tool, dict):
            return None
        name = tool.get("name")
        description = tool.get("description")
        parameters = tool.get("parameters")
        if not isinstance(name, str) or not isinstance(description, str) or not isinstance(parameters, dict):
            return None
        typed_tools.append({"name": name, "description": description, "parameters": parameters})
    calls = gold.get("calls")
    order_matters = gold.get("order_matters")
    if not isinstance(calls, list) or not isinstance(order_matters, bool):
        return None
    typed_calls: list[ToolCall] = []
    for call in calls:
        if not isinstance(call, dict) or not isinstance(call.get("name"), str) or not isinstance(call.get("arguments"), dict):
            return None
        typed_calls.append({"name": call["name"], "arguments": call["arguments"]})
    normalizers = policy.get("normalizers")
    unordered_arrays = policy.get("unordered_arrays")
    if not isinstance(normalizers, dict) or not isinstance(unordered_arrays, list):
        return None
    item_id = prompt_item.get("id")
    source = prompt_item.get("source")
    stratum = prompt_item.get("stratum")
    prompt = prompt_item.get("prompt")
    if not all(isinstance(value, str) for value in (item_id, source, stratum, prompt)):
        return None
    return {
        "id": item_id,
        "source": source,
        "stratum": stratum,
        "prompt": prompt,
        "tools": typed_tools,
        "gold": {"order_matters": order_matters, "calls": typed_calls},
        "match_policy": {
            "default": str(policy.get("default", "")),
            "normalizers": {str(key): str(value) for key, value in normalizers.items()},
            "allow_default_omission": bool(policy.get("allow_default_omission")),
            "unordered_arrays": [item for item in unordered_arrays if isinstance(item, str)],
        },
    }


def _failure(
    reason: TCJsonScore["failure_reason"],
    extracted: str | None,
    schema_version: str | None,
    *,
    schema_valid: bool = False,
    diagnostics: FailureDiagnostics | None = None,
) -> TCJsonScore:
    return {
        "correct": False,
        "extracted": extracted,
        "failure_reason": reason,
        "diagnostics": diagnostics or _empty_diagnostics(),
        "response_schema_valid": schema_valid,
        "schema_version": schema_version,
    }


def _count_diagnostics(predicted: list[ToolCall], gold: list[ToolCall]) -> FailureDiagnostics:
    diagnostics = _empty_diagnostics()
    if len(predicted) > len(gold):
        diagnostics["extra_call"] = predicted[len(gold) :]
    if len(gold) > len(predicted):
        diagnostics["missing_call"] = gold[len(predicted) :]
    return diagnostics


def _empty_diagnostics() -> FailureDiagnostics:
    return {"extra_call": [], "missing_call": [], "arg_mismatch": []}


def _schema_version(value: Mapping[str, JsonValue]) -> str | None:
    schema_version = value.get("schema_version")
    return schema_version if isinstance(schema_version, str) else None

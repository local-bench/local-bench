from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from localbench.scorers.tc_json_v1 import build_tc_json_prompt, score_tc_json_v1
from localbench.scorers.tc_json_v1._types import JsonValue


def _call(name: str, arguments: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {"name": name, "arguments": arguments}


def _response(calls: list[dict[str, JsonValue]]) -> str:
    return json.dumps({"schema_version": "localbench.tc.v1", "calls": calls})


def test_build_tc_json_prompt_when_given_item_renders_catalog_and_rules() -> None:
    item = _item([_weather_tool()], [_call("weather.get", {"location": "Brisbane"})])
    template = "Tools:\n{tool_catalog}\nRequest:\n{user_request}\nNo prose."

    prompt = build_tc_json_prompt(item, template)

    assert "weather.get" in prompt
    assert "Need weather." in prompt
    assert "No prose." in prompt


@pytest.mark.parametrize(
    ("response", "correct", "failure"),
    [
        (_response([_call("weather.get", {"location": "Brisbane"})]), True, None),
        ("not json", False, "invalid_json"),
        ("```json\n{}\n```", False, "response_schema_invalid"),
        (_response([]) + _response([]), False, "extra_text_or_multiple_json_objects"),
        ("Here: " + _response([]), False, "invalid_json"),
        (json.dumps({"schema_version": "wrong", "calls": []}), False, "wrong_schema_version"),
        (json.dumps({"schema_version": "localbench.tc.v1", "calls": [], "extra": 1}), False, "response_schema_invalid"),
        (_response([]), False, "wrong_call_count"),
        (_response([_call("web.search", {"query": "Brisbane weather"})]), False, "wrong_tool"),
        (_response([_call("weather.get", {"location": 123})]), False, "arg_schema_invalid"),
        (_response([_call("weather.get", {"location": "Sydney"})]), False, "call_or_arg_mismatch"),
    ],
)
def test_score_tc_json_v1_when_response_varies_returns_expected_taxonomy(
    response: str,
    correct: bool,
    failure: str | None,
) -> None:
    item = _item([_weather_tool()], [_call("weather.get", {"location": "Brisbane"})])

    score = score_tc_json_v1(item, response)

    assert score["correct"] is correct
    assert score["failure_reason"] == failure
    assert set(score["diagnostics"]) == {"extra_call", "missing_call", "arg_mismatch"}


@pytest.mark.parametrize(
    "response",
    [
        _response([_call("weather.get", {"location": "Brisbane"})]),
        f"<think>scratch</think>{_response([_call('weather.get', {'location': 'Brisbane'})])}",
        f"<think>scratch</think>\n```json\n{_response([_call('weather.get', {'location': 'Brisbane'})])}\n```",
        f"```\n{_response([_call('weather.get', {'location': 'Brisbane'})])}\n```",
    ],
)
def test_score_tc_json_v1_when_valid_envelope_has_tolerated_extraction_wrappers_scores_correct(response: str) -> None:
    # Given a valid item whose gold call exactly matches the model envelope.
    item = _item([_weather_tool()], [_call("weather.get", {"location": "Brisbane"})])

    # When the response is scored with optional reasoning and fence wrappers.
    score = score_tc_json_v1(item, response)

    # Then extraction tolerance does not change strict correctness.
    assert score["correct"] is True
    assert score["failure_reason"] is None


def test_score_tc_json_v1_when_think_block_is_unclosed_returns_invalid_json() -> None:
    # Given a response still inside an unclosed reasoning block.
    item = _item([_weather_tool()], [_call("weather.get", {"location": "Brisbane"})])
    response = f"<think>scratch {_response([_call('weather.get', {'location': 'Brisbane'})])}"

    # When the response is scored.
    score = score_tc_json_v1(item, response)

    # Then no scratch content is credited as an answer.
    assert score["correct"] is False
    assert score["failure_reason"] == "invalid_json"


def test_score_tc_json_v1_when_answer_has_trailing_prose_after_reasoning_still_rejects_extra_text() -> None:
    # Given a valid envelope followed by prose after a complete reasoning block.
    item = _item([_weather_tool()], [_call("weather.get", {"location": "Brisbane"})])
    response = f"<think>scratch</think>{_response([_call('weather.get', {'location': 'Brisbane'})])} trailing prose"

    # When the response is scored.
    score = score_tc_json_v1(item, response)

    # Then the strict single-object rule still rejects trailing text.
    assert score["correct"] is False
    assert score["failure_reason"] == "extra_text_or_multiple_json_objects"


@pytest.mark.parametrize(
    ("response", "failure"),
    [
        (
            json.dumps(
                {
                    "schema_version": "wrong",
                    "calls": [_call("weather.get", {"location": "Brisbane"})],
                }
            ),
            "wrong_schema_version",
        ),
        (_response([_call("web.search", {"query": "Brisbane weather"})]), "wrong_tool"),
        (_response([_call("weather.get", {"location": 123})]), "arg_schema_invalid"),
        (_response([_call("weather.get", {"location": "Sydney"})]), "call_or_arg_mismatch"),
    ],
)
def test_score_tc_json_v1_when_invalid_envelope_has_reasoning_prefix_keeps_validation_failure(
    response: str,
    failure: str,
) -> None:
    # Given a bare invalid envelope and the same envelope behind a reasoning block.
    item = _item([_weather_tool()], [_call("weather.get", {"location": "Brisbane"})])

    # When both responses are scored.
    bare = score_tc_json_v1(item, response)
    prefixed = score_tc_json_v1(item, f"<think>scratch</think>{response}")

    # Then hardening does not rescue genuinely wrong calls or schema versions.
    assert bare["correct"] is False
    assert bare["failure_reason"] == failure
    assert prefixed["correct"] is False
    assert prefixed["failure_reason"] == failure
    assert prefixed["extracted"] == bare["extracted"]


def test_score_tc_json_v1_when_malformed_inputs_never_raises() -> None:
    score = score_tc_json_v1({"id": "bad"}, "{")

    assert score["correct"] is False
    assert score["failure_reason"] in {"invalid_json", "response_schema_invalid"}


def test_normalize_value_when_normalizer_id_is_unknown_falls_back_to_nfc_not_none() -> None:
    # Regression guard: an unknown / mistyped normalizer id must fall back to a plain NFC
    # string compare, never an implicit None — otherwise both gold and predicted collapse
    # to None and ANY value is accepted (a silent false-pass the gold-self-score gate, which
    # only ever scores gold == gold, cannot catch).
    from localbench.scorers.tc_json_v1._parser import _normalize_value

    policy = {"normalizers": {"/v": "bogus_id"}}
    assert _normalize_value("alpha", "/v", policy) == "alpha"
    assert _normalize_value("alpha", "/v", policy) != _normalize_value("beta", "/v", policy)


def test_score_tc_json_v1_when_no_call_item_scores_empty_call_list_only() -> None:
    item = _item([_weather_tool()], [])

    correct = score_tc_json_v1(item, _response([]))
    wrong = score_tc_json_v1(item, _response([_call("weather.get", {"location": "Brisbane"})]))

    assert correct["correct"] is True
    assert wrong["correct"] is False
    assert wrong["failure_reason"] == "wrong_call_count"


def test_score_tc_json_v1_when_arguments_are_missing_or_extra_reports_arg_schema_invalid() -> None:
    item = _item([_weather_tool()], [_call("weather.get", {"location": "Brisbane"})])

    missing = score_tc_json_v1(item, _response([_call("weather.get", {})]))
    extra = score_tc_json_v1(item, _response([_call("weather.get", {"location": "Brisbane", "x": 1})]))

    assert missing["failure_reason"] == "arg_schema_invalid"
    assert extra["failure_reason"] == "arg_schema_invalid"


def test_score_tc_json_v1_when_order_does_not_matter_uses_bipartite_match() -> None:
    first = _call("timer.set", {"duration_minutes": 5, "label": "tea"})
    second = _call("timer.set", {"duration_minutes": 30, "label": "laundry"})
    item = _item([_timer_tool()], [first, second], order_matters=False)

    score = score_tc_json_v1(item, _response([second, first]))

    assert score["correct"] is True


def test_score_tc_json_v1_when_order_matters_rejects_reordered_calls() -> None:
    first = _call("timer.set", {"duration_minutes": 5, "label": "tea"})
    second = _call("timer.set", {"duration_minutes": 30, "label": "laundry"})
    item = _item([_timer_tool()], [first, second], order_matters=True)

    score = score_tc_json_v1(item, _response([second, first]))

    assert score["correct"] is False
    assert score["failure_reason"] == "call_or_arg_mismatch"


def test_score_tc_json_v1_when_unordered_array_policy_is_set_ignores_array_order() -> None:
    tool = _tool(
        "email.send",
        {
            "to": {"type": "string"},
            "cc": {"type": "array", "items": {"type": "string"}},
        },
        ["to", "cc"],
    )
    item = _item(
        [tool],
        [_call("email.send", {"to": "ops@example.com", "cc": ["a@example.com", "b@example.com"]})],
        unordered_arrays=["/cc"],
    )

    score = score_tc_json_v1(item, _response([_call("email.send", {"to": "ops@example.com", "cc": ["b@example.com", "a@example.com"]})]))

    assert score["correct"] is True


def test_score_tc_json_v1_when_normalizers_are_declared_applies_them() -> None:
    tool = _tool(
        "calendar.create_event",
        {
            "date": {"type": "string"},
            "time": {"type": "string"},
            "priority": {"type": "string", "enum": ["HIGH", "LOW"]},
        },
        ["date", "time", "priority"],
    )
    item = _item(
        [tool],
        [_call("calendar.create_event", {"date": "2026-07-02", "time": "09:30", "priority": "HIGH"})],
        normalizers={"/date": "iso_date", "/time": "hhmm_24h", "/priority": "enum-casefold"},
    )

    score = score_tc_json_v1(item, _response([_call("calendar.create_event", {"date": "2026-07-02", "time": "09:30:00", "priority": "high"})]))

    assert score["correct"] is True


def test_score_tc_json_v1_when_default_omission_is_allowed_fills_schema_defaults() -> None:
    tool = _tool("todo.add", {"title": {"type": "string"}, "priority": {"type": "string", "default": "medium"}}, ["title"])
    item = _item([tool], [_call("todo.add", {"title": "file expenses"})], allow_default_omission=True)

    score = score_tc_json_v1(item, _response([_call("todo.add", {"title": "file expenses", "priority": "medium"})]))

    assert score["correct"] is True


def test_score_tc_json_v1_when_default_omission_is_not_allowed_requires_exact_keys() -> None:
    tool = _tool("todo.add", {"title": {"type": "string"}, "priority": {"type": "string", "default": "medium"}}, ["title"])
    item = _item([tool], [_call("todo.add", {"title": "file expenses"})], allow_default_omission=False)

    score = score_tc_json_v1(item, _response([_call("todo.add", {"title": "file expenses", "priority": "medium"})]))

    assert score["correct"] is False
    assert score["failure_reason"] == "call_or_arg_mismatch"


def _item(
    tools: list[dict[str, JsonValue]],
    calls: list[dict[str, JsonValue]],
    *,
    order_matters: bool = True,
    normalizers: Mapping[str, str] | None = None,
    unordered_arrays: list[str] | None = None,
    allow_default_omission: bool = True,
) -> dict[str, JsonValue]:
    return {
        "id": "tc-json-test",
        "source": "test",
        "stratum": "unit",
        "prompt": "Need weather.",
        "tools": tools,
        "gold": {"order_matters": order_matters, "calls": calls},
        "match_policy": {
            "default": "typed_canonical_json_equality",
            "normalizers": dict(normalizers or {}),
            "allow_default_omission": allow_default_omission,
            "unordered_arrays": unordered_arrays or [],
        },
    }


def _tool(name: str, properties: dict[str, JsonValue], required: list[str]) -> dict[str, JsonValue]:
    return {
        "name": name,
        "description": name,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


def _weather_tool() -> dict[str, JsonValue]:
    return _tool("weather.get", {"location": {"type": "string"}}, ["location"])


def _timer_tool() -> dict[str, JsonValue]:
    return _tool(
        "timer.set",
        {"duration_minutes": {"type": "integer"}, "label": {"type": "string"}},
        ["duration_minutes", "label"],
    )

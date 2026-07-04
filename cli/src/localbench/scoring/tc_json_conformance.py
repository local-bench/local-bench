from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.scoring.board_support import int_value, number_value, object_value

GATE_ID: Final = "tc_json_v1"
GATE_LABEL: Final = "Tool-calling"


def tc_json_conformance_gate(aggregate: Mapping[str, JsonValue]) -> JsonObject:
    raw_asr = number_value(aggregate.get("raw_asr"), "tc_json.aggregate.raw_asr")
    invalid_json_rate = number_value(aggregate.get("invalid_json_rate"), "tc_json.aggregate.invalid_json_rate")
    ci = object_value(aggregate.get("wilson_95_ci"), "tc_json.aggregate.wilson_95_ci")
    band, reasons = _band_and_reasons(raw_asr * 100.0, invalid_json_rate * 100.0)
    return {
        "id": GATE_ID,
        "label": GATE_LABEL,
        "band": band,
        "pass_rate": {
            "point": number_value(ci.get("point"), "tc_json.aggregate.wilson_95_ci.point") * 100.0,
            "lo": number_value(ci.get("lo"), "tc_json.aggregate.wilson_95_ci.lo") * 100.0,
            "hi": number_value(ci.get("hi"), "tc_json.aggregate.wilson_95_ci.hi") * 100.0,
        },
        "invalid_json_rate": invalid_json_rate * 100.0,
        "n_items": int_value(aggregate.get("n"), "tc_json.aggregate.n"),
        "threshold_version": GATE_ID,
        "band_reasons": reasons,
    }


def _band_and_reasons(pass_rate: float, invalid_json_rate: float) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if pass_rate < 60.0:
        reasons.append("pass<60")
    if invalid_json_rate > 15.0:
        reasons.append("invalid_json>15")
    if reasons:
        return "red", reasons
    if pass_rate >= 80.0 and invalid_json_rate <= 5.0:
        return "green", reasons
    if invalid_json_rate > 5.0:
        reasons.append("invalid_json>5")
    return "amber", reasons

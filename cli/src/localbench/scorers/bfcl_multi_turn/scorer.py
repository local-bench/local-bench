from __future__ import annotations

import json
from collections.abc import Mapping

from localbench.scorers.bfcl_multi_turn._executor import score_trace_against_gold
from localbench.scorers.bfcl_multi_turn._parser import decode_action_trace, encode_trace
from localbench.scorers.bfcl_multi_turn._types import (
    ActionTrace,
    BFCLMultiTurnScore,
    FailureKind,
    JsonValue,
)


def score_bfcl_multi_turn(
    prompt_item: Mapping[str, JsonValue],
    response_text: str,
) -> BFCLMultiTurnScore:
    trace = decode_action_trace(response_text if isinstance(response_text, str) else "")
    if trace is None:
        return _score(False, None, FailureKind.MALFORMED_CALL)
    gold = _gold_trace(prompt_item)
    if gold is None:
        return _score(False, encode_trace(trace), FailureKind.WRONG_FINAL_RESPONSE)
    correct, failure_kind, details = score_trace_against_gold(
        item=prompt_item,
        model_trace=trace,
        gold_trace=gold,
    )
    if failure_kind is FailureKind.MALFORMED_CALL:
        return _score(False, None, failure_kind)
    return _score(correct, _extracted(trace, details), failure_kind)


def _gold_trace(prompt_item: Mapping[str, JsonValue]) -> ActionTrace | None:
    value = prompt_item.get("ground_truth")
    if not isinstance(value, list):
        return None
    trace: ActionTrace = []
    for turn in value:
        if not isinstance(turn, list) or not all(isinstance(call, str) for call in turn):
            return None
        trace.append([str(call) for call in turn])
    return trace


def _extracted(trace: ActionTrace, details: Mapping[str, JsonValue]) -> str:
    return json.dumps(
        {"trace": trace, "final_state": details.get("final_state", {})},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _score(
    correct: bool,
    extracted: str | None,
    failure_kind: FailureKind | None,
) -> BFCLMultiTurnScore:
    return {
        "correct": correct,
        "extracted": extracted,
        "failure_kind": failure_kind.value if failure_kind is not None else None,
    }

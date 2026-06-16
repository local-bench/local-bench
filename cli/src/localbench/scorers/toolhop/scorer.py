from __future__ import annotations

import json
from collections.abc import Mapping

from localbench.scorers.toolhop._answer import answer_matches
from localbench.scorers.toolhop._executor import execute_toolhop_trace
from localbench.scorers.toolhop._parser import decode_tool_trace
from localbench.scorers.toolhop._types import FailureKind, JsonValue, ToolHopScore, TraceExecution


def score_toolhop(
    prompt_item: Mapping[str, JsonValue],
    response_text: str,
) -> ToolHopScore:
    trace = decode_tool_trace(response_text if isinstance(response_text, str) else "")
    if trace is None:
        return _score(False, None, FailureKind.MALFORMED_CALL)
    execution = execute_toolhop_trace(item=prompt_item, trace=trace)
    if execution.failure_kind is not None:
        extracted = None if execution.failure_kind is FailureKind.MALFORMED_CALL else _extracted(execution)
        return _score(False, extracted, execution.failure_kind)
    expected = prompt_item.get("answer")
    answer_type = prompt_item.get("answer_type")
    final_output = execution.outputs[-1] if execution.outputs else None
    correct = (
        isinstance(expected, str)
        and isinstance(answer_type, str)
        and answer_matches(expected=expected, answer_type=answer_type, output=final_output)
    )
    return _score(
        correct,
        _extracted(execution),
        None if correct else FailureKind.WRONG_FINAL_ANSWER,
    )


def _extracted(execution: TraceExecution) -> str:
    final_output = execution.outputs[-1] if execution.outputs else None
    return json.dumps(
        {
            "trace": execution.calls,
            "outputs": execution.outputs,
            "final_output": final_output,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _score(
    correct: bool,
    extracted: str | None,
    failure_kind: FailureKind | None,
) -> ToolHopScore:
    return {
        "correct": correct,
        "extracted": extracted,
        "failure_kind": failure_kind.value if failure_kind is not None else None,
    }

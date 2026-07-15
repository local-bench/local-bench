from __future__ import annotations

import json
from pathlib import Path
from typing import Final, TypeAlias

from localbench.scorers.bfcl_multi_turn import (
    FailureKind,
    build_bfcl_multi_turn_prompt,
    score_bfcl_multi_turn,
)
from localbench.scorers.bfcl_multi_turn._executor import execute_trace

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
_SOURCE_DIR: Final = (
    _REPO_ROOT
    / "suite"
    / "v2"
)


def test_score_bfcl_multi_turn_when_trace_matches_gold_is_deterministic() -> None:
    # Given a real vendored multi-turn item and its known-correct trace.
    item = _source_item("bfcl_multi_turn_base.jsonl", "multi_turn_base_0")
    response = json.dumps(item["ground_truth"])

    # When scoring the same trace twice.
    first = score_bfcl_multi_turn(item, response)
    second = score_bfcl_multi_turn(item, response)

    # Then correctness, extraction, and final state are stable.
    assert first == second
    assert first["correct"] is True
    assert first["failure_kind"] is None
    assert first["extracted"] is not None


def test_score_bfcl_multi_turn_when_trace_has_wrong_args_reports_wrong_state() -> None:
    # Given a real file-system item with a trace that moves the wrong file name.
    item = _source_item("bfcl_multi_turn_base.jsonl", "multi_turn_base_0")
    wrong_trace = [
        ["ls(a=True)"],
        ["cd(folder='workspace')", "mv(source='missing.txt',destination='archive')"],
        ["cd(folder='archive')", "grep(file_name='log.txt',pattern='Error')"],
        ["tail(file_name='log.txt',lines=20)"],
    ]

    # When scoring the wrong trace twice.
    first = score_bfcl_multi_turn(item, json.dumps(wrong_trace))
    second = score_bfcl_multi_turn(item, json.dumps(wrong_trace))

    # Then the scorer is deterministic and records the state-reasoning failure.
    assert first == second
    assert first["correct"] is False
    assert first["failure_kind"] == FailureKind.WRONG_STATE


def test_score_bfcl_multi_turn_when_call_is_malformed_reports_taxonomy() -> None:
    # Given a malformed model action sequence.
    item = _source_item("bfcl_multi_turn_base.jsonl", "multi_turn_base_0")

    # When the response cannot be parsed as a trace.
    result = score_bfcl_multi_turn(item, "[[\"ls(a=True)\", \"cd(folder=\"]]")

    # Then call syntax failure is separated from state mismatch.
    assert result["correct"] is False
    assert result["extracted"] is None
    assert result["failure_kind"] == FailureKind.MALFORMED_CALL


def test_score_bfcl_multi_turn_when_call_uses_unknown_tool_reports_wrong_tool() -> None:
    # Given a model trace that attempts to use a non-advertised dangerous tool.
    item = _source_item("bfcl_multi_turn_base.jsonl", "multi_turn_base_0")
    trace = [["open('owned.txt', 'w')"]]

    # When scoring the trace.
    result = score_bfcl_multi_turn(item, json.dumps(trace))

    # Then it is blocked by construction before any filesystem write can occur.
    assert result["correct"] is False
    assert result["failure_kind"] == FailureKind.WRONG_TOOL
    assert not (_REPO_ROOT / "owned.txt").exists()


def test_score_bfcl_multi_turn_when_signature_does_not_bind_reports_wrong_args() -> None:
    # Given a trace that calls a real advertised tool with an unexpected argument.
    item = _source_item("bfcl_multi_turn_base.jsonl", "multi_turn_base_0")
    trace = [["ls(a=True, unexpected=1)"]]

    # When scoring the trace.
    result = score_bfcl_multi_turn(item, json.dumps(trace))

    # Then argument binding failure is separated from choosing the wrong tool.
    assert result["correct"] is False
    assert result["failure_kind"] == FailureKind.WRONG_ARGS


def test_score_bfcl_multi_turn_when_required_turn_is_empty_reports_wrong_final_response() -> None:
    # Given a trace that emits no call for a turn where gold requires work.
    item = _source_item("bfcl_multi_turn_base.jsonl", "multi_turn_base_0")

    # When scoring the trace.
    result = score_bfcl_multi_turn(item, json.dumps([[]]))

    # Then missing action is classified as final-response failure, not syntax failure.
    assert result["correct"] is False
    assert result["failure_kind"] == FailureKind.WRONG_FINAL_RESPONSE


def test_execute_trace_when_timeout_budget_is_exhausted_reports_timeout() -> None:
    # Given a valid trace but a zero execution budget.
    item = _source_item("bfcl_multi_turn_base.jsonl", "multi_turn_base_0")

    # When executing under the exhausted budget.
    result = execute_trace(
        item=item,
        trace=[["ls(a=True)"]],
        timeout_seconds=0.0,
    )

    # Then timeout is reported through the failure taxonomy.
    assert result.failure_kind == FailureKind.TIMEOUT


def test_build_bfcl_multi_turn_prompt_when_given_item_includes_trace_contract() -> None:
    # Given a real multi-turn item.
    item = _source_item("bfcl_multi_turn_base.jsonl", "multi_turn_base_0")

    # When building the prompt used by suite rendering.
    prompt = build_bfcl_multi_turn_prompt(item)

    # Then it exposes turns, tools, initial state, and the exact action-sequence contract.
    assert "Return only a JSON array" in prompt
    assert "Turn 1" in prompt
    assert "GorillaFileSystem" in prompt
    assert "initial_config" in prompt


def _source_item(file_name: str, source_id: str) -> JsonObject:
    prompt_rows = _load_jsonl(_SOURCE_DIR / file_name)
    for row in prompt_rows:
        if row.get("source_id") == source_id:
            return row
    raise AssertionError(f"Missing BFCL source item {source_id}")


def _load_jsonl(path: Path) -> list[JsonObject]:
    rows: list[JsonObject] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise AssertionError(f"{path.name} contains a non-object row")
            rows.append(parsed)
    return rows


def _str_list(value: JsonValue) -> list[str]:
    if not isinstance(value, list):
        raise AssertionError("expected list")
    return [item for item in value if isinstance(item, str)]

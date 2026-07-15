from __future__ import annotations

from localbench._types import JsonObject, JsonValue
from localbench.scoring.agentic_exec.loop_types import (
    FailureClass,
    TaskDiagnostics,
    TaskOutcome,
    TaskRunResult,
    TurnRecord,
)
from localbench.scoring.agentic_exec.task_journal_types import JournalCorruptionError


def task_result_from_envelope(envelope: JsonObject) -> TaskRunResult:
    result = _object(envelope.get("result"), "result")
    diagnostics = _object(envelope.get("diagnostics"), "diagnostics")
    task_id = _string(result.get("task_id"), "result.task_id")
    outcome = _outcome(result.get("outcome"))
    success = _boolean(result.get("success"), "result.success")
    collateral_damage = _boolean(
        result.get("collateral_damage"),
        "result.collateral_damage",
    )
    parsed_diagnostics = TaskDiagnostics(
        task_id=_string(diagnostics.get("task_id"), "diagnostics.task_id"),
        outcome=_outcome(diagnostics.get("outcome")),
        success=_boolean(diagnostics.get("success"), "diagnostics.success"),
        collateral_damage=_boolean(
            diagnostics.get("collateral_damage"),
            "diagnostics.collateral_damage",
        ),
        turns_used=_integer(diagnostics.get("turns_used"), "diagnostics.turns_used"),
        blocks_run=_integer(diagnostics.get("blocks_run"), "diagnostics.blocks_run"),
        format_failures=_integer(
            diagnostics.get("format_failures"),
            "diagnostics.format_failures",
        ),
        syntax_errors=_integer(diagnostics.get("syntax_errors"), "diagnostics.syntax_errors"),
        runtime_errors=_integer(
            diagnostics.get("runtime_errors"),
            "diagnostics.runtime_errors",
        ),
        cap_exceeded=_boolean(diagnostics.get("cap_exceeded"), "diagnostics.cap_exceeded"),
        total_api_calls=_integer(
            diagnostics.get("total_api_calls"),
            "diagnostics.total_api_calls",
        ),
        api_docs_uses=_integer(
            diagnostics.get("api_docs_uses"),
            "diagnostics.api_docs_uses",
        ),
        observation_truncations=_integer(
            diagnostics.get("observation_truncations"),
            "diagnostics.observation_truncations",
        ),
        total_output_tokens=_integer(
            diagnostics.get("total_output_tokens"),
            "diagnostics.total_output_tokens",
        ),
        finalize_error=_optional_string(diagnostics.get("finalize_error"), "finalize_error"),
        finalization=_optional_object(diagnostics.get("finalization"), "finalization"),
        turns=_turns(diagnostics.get("turns")),
        failure_class=_failure_class(diagnostics.get("failure_class")),
        transport_failure_count=_integer(
            diagnostics.get("transport_failure_count"),
            "diagnostics.transport_failure_count",
        ),
        transport_attempt_count=_integer(
            diagnostics.get("transport_attempt_count"),
            "diagnostics.transport_attempt_count",
        ),
        transport_failure_rate=_number(
            diagnostics.get("transport_failure_rate"),
            "diagnostics.transport_failure_rate",
        ),
        teardown_failure_count=_integer(
            diagnostics.get("teardown_failure_count"),
            "diagnostics.teardown_failure_count",
        ),
        teardown_failure_detail=_optional_string(
            diagnostics.get("teardown_failure_detail"),
            "teardown_failure_detail",
        ),
    )
    if (
        parsed_diagnostics.task_id != task_id
        or parsed_diagnostics.outcome is not outcome
        or parsed_diagnostics.success is not success
        or parsed_diagnostics.collateral_damage is not collateral_damage
    ):
        raise JournalCorruptionError("committed result and diagnostics disagree")
    attestation = _optional_object(envelope.get("attestation"), "attestation")
    return TaskRunResult(
        task_id=task_id,
        success=success,
        outcome=outcome,
        collateral_damage=collateral_damage,
        diagnostics=parsed_diagnostics,
        attestation=attestation,
    )


def _turns(value: JsonValue | None) -> list[TurnRecord]:
    if not isinstance(value, list):
        raise JournalCorruptionError("journal diagnostics.turns must be a list")
    return [_turn(_object(item, "turn")) for item in value]


def _turn(value: JsonObject) -> TurnRecord:
    return TurnRecord(
        index=_integer(value.get("index"), "turn.index"),
        finish_reason=_string(value.get("finish_reason"), "turn.finish_reason"),
        output_tokens=_integer(value.get("output_tokens"), "turn.output_tokens"),
        had_block=_boolean(value.get("had_block"), "turn.had_block"),
        format_error=_optional_string(value.get("format_error"), "turn.format_error"),
        syntax_error=_boolean(value.get("syntax_error"), "turn.syntax_error"),
        runtime_error=_boolean(value.get("runtime_error"), "turn.runtime_error"),
        api_calls=_integer(value.get("api_calls"), "turn.api_calls"),
        api_docs_calls=_integer(value.get("api_docs_calls"), "turn.api_docs_calls"),
        observation_truncated=_boolean(
            value.get("observation_truncated"),
            "turn.observation_truncated",
        ),
        is_final=_boolean(value.get("is_final"), "turn.is_final"),
        raw_response_text=_string(value.get("raw_response_text"), "turn.raw_response_text"),
        error_detail=_optional_string(value.get("error_detail"), "turn.error_detail"),
        server_timings=_optional_object(value.get("server_timings"), "turn.server_timings"),
    )


def _outcome(value: JsonValue | None) -> TaskOutcome:
    try:
        return TaskOutcome(_string(value, "outcome"))
    except ValueError as error:
        raise JournalCorruptionError(f"journal task outcome is invalid: {value!r}") from error


def _failure_class(value: JsonValue | None) -> FailureClass:
    try:
        return FailureClass(_string(value, "failure_class"))
    except ValueError as error:
        raise JournalCorruptionError(f"journal failure class is invalid: {value!r}") from error


def _object(value: JsonValue | None, field: str) -> JsonObject:
    if not isinstance(value, dict):
        raise JournalCorruptionError(f"journal {field} must be an object")
    return value


def _optional_object(value: JsonValue | None, field: str) -> JsonObject | None:
    if value is None:
        return None
    return _object(value, field)


def _string(value: JsonValue | None, field: str) -> str:
    if not isinstance(value, str):
        raise JournalCorruptionError(f"journal {field} must be a string")
    return value


def _optional_string(value: JsonValue | None, field: str) -> str | None:
    if value is None:
        return None
    return _string(value, field)


def _integer(value: JsonValue | None, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise JournalCorruptionError(f"journal {field} must be an integer")
    return value


def _number(value: JsonValue | None, field: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise JournalCorruptionError(f"journal {field} must be a number")
    return float(value)


def _boolean(value: JsonValue | None, field: str) -> bool:
    if not isinstance(value, bool):
        raise JournalCorruptionError(f"journal {field} must be a boolean")
    return value

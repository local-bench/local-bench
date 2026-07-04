"""Assistant-turn parser with the spec's one-retry failure policy."""

from __future__ import annotations

import json
from json import JSONDecodeError

from localbench._types import JsonValue
from localbench.scoring.agentic_exec.config import AgenticExecConfig
from localbench.scoring.agentic_exec.protocol import parse_assistant_action
from localbench.scoring.agentic_exec.types import (
    ActionSchemaError,
    FailureReason,
    ParseFailure,
    ParseOutcome,
)


class AssistantActionParser:
    """Parse exactly one JSON object per assistant turn."""

    def __init__(self, config: AgenticExecConfig) -> None:
        self._config = config
        self._recoverable_failures = 0

    def parse_turn(self, raw_text: str, *, finish_reason: str | None = None) -> ParseOutcome:
        """Parse one assistant turn or return a deterministic failure."""
        hard_failure = _finish_reason_failure(finish_reason)
        if hard_failure is not None:
            return ParseOutcome(action=None, failure=hard_failure)

        decoded = self._decode_exact_object(raw_text)
        if decoded is None:
            return self._recoverable_failure(
                FailureReason.INVALID_JSON,
                "assistant turn must contain exactly one JSON object",
            )
        try:
            action = parse_assistant_action(decoded)
        except ActionSchemaError as exc:
            return self._recoverable_failure(FailureReason.SCHEMA_ERROR, exc.message)

        self._recoverable_failures = 0
        return ParseOutcome(action=action, failure=None)

    def _decode_exact_object(self, raw_text: str) -> JsonValue | None:
        decoder = json.JSONDecoder()
        try:
            decoded, end_index = decoder.raw_decode(raw_text)
        except JSONDecodeError:
            return None
        if raw_text[end_index:].strip():
            return None
        match decoded:  # noqa: MATCH_OK - decoded JSON is open input.
            case dict():
                return decoded
            case _:
                return None

    def _recoverable_failure(
        self,
        reason: FailureReason,
        message: str,
    ) -> ParseOutcome:
        if self._recoverable_failures >= self._config.parse_retries:
            return ParseOutcome(
                action=None,
                failure=ParseFailure(
                    reason=FailureReason.MAX_RETRIES_EXCEEDED,
                    message=message,
                    hard_fail=True,
                ),
            )
        self._recoverable_failures += 1
        return ParseOutcome(
            action=None,
            failure=ParseFailure(reason=reason, message=message, hard_fail=False),
        )


def _finish_reason_failure(finish_reason: str | None) -> ParseFailure | None:
    match finish_reason:  # noqa: MATCH_OK - provider finish reasons are open strings.
        case "timeout":
            return ParseFailure(
                reason=FailureReason.TIMEOUT,
                message="assistant generation timed out",
                hard_fail=True,
            )
        case "length":
            return ParseFailure(
                reason=FailureReason.LENGTH,
                message="assistant generation hit the per-turn token cap",
                hard_fail=True,
            )
        case _:
            return None

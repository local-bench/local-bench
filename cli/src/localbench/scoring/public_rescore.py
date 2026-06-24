from __future__ import annotations

from collections.abc import Mapping

from localbench._scoring import ResponseScore, _score_response_detail
from localbench._types import JsonValue


def score_public_item(
    bench: str,
    suite_item: Mapping[str, JsonValue],
    response_text: str | None,
    *,
    error: str | None = None,
    finish_reason: str | None = None,
) -> ResponseScore:
    detailed = _score_response_detail(bench, suite_item, response_text, error, finish_reason)
    if finish_reason == "length":
        return {**detailed, "correct": False}
    return detailed

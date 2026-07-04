from __future__ import annotations

from collections.abc import Mapping

from localbench._scoring import ScoredItem, aggregate, composite, run_totals
from localbench._types import JsonObject, JsonValue, Usage
from localbench.scoring.public_rescore import score_public_item
from localbench.submissions.validate import SuiteItem, SubmissionValidationError


def recompute_public_scores(
    items: list[JsonObject],
    suite_items: Mapping[tuple[str, str], SuiteItem],
    dynamic_benches: frozenset[str] = frozenset(),
) -> JsonObject:
    scored = [_rescore_item(item, suite_items, dynamic_benches) for item in items]
    baselines = _baselines(suite_items) | {bench: 0.0 for bench in dynamic_benches}
    benches = {
        bench: aggregate(bench, [item for item in scored if item["bench"] == bench], baseline)
        for bench, baseline in baselines.items()
        if any(item["bench"] == bench for item in scored)
    }
    return {
        "items": [_public_item(item) for item in scored],
        "benches": benches,
        "composite": composite(benches),
        "totals": run_totals(scored, _wall_time(scored)),
    }


def _rescore_item(
    item: JsonObject,
    suite_items: Mapping[tuple[str, str], SuiteItem],
    dynamic_benches: frozenset[str],
) -> ScoredItem:
    bench = _string_or_error(item.get("bench"), "bench")
    item_id = _string_or_error(item.get("item_id"), "item_id")
    suite_item = suite_items.get((bench, item_id))
    if suite_item is None:
        if bench in dynamic_benches:
            return _verdict_carried_item(item, bench, item_id)
        raise SubmissionValidationError(f"unknown item: {bench}/{item_id}")
    response = _object(item.get("response"))
    timing = _object(item.get("timing"))
    detail = score_public_item(
        bench,
        suite_item.source,
        _optional_string(response.get("text")),
        error=_optional_string(response.get("error")),
        finish_reason=_optional_string(response.get("finish_reason")),
    )
    scored: ScoredItem = {
        "id": item_id,
        "bench": bench,
        "response_text": _optional_string(response.get("text")),
        "extracted": detail["extracted"],
        "correct": detail["correct"],
        "finish_reason": _optional_string(response.get("finish_reason")),
        "latency_seconds": _number(timing.get("latency_seconds")),
        "started_at": _optional_string(timing.get("started_at")) or "",
        "finished_at": _optional_string(timing.get("finished_at")) or "",
        "attempts": _int(timing.get("attempts")),
        "usage": _usage(item.get("usage")),
        "error": _optional_string(response.get("error")),
    }
    if "failure_kind" in detail:
        scored["failure_kind"] = detail["failure_kind"]
    return scored


def _verdict_carried_item(item: JsonObject, bench: str, item_id: str) -> ScoredItem:
    response = _object(item.get("response"))
    timing = _object(item.get("timing"))
    client_scoring = _object(item.get("client_scoring"))
    return {
        "id": item_id,
        "bench": bench,
        "response_text": _optional_string(response.get("text")),
        "extracted": _optional_string(client_scoring.get("extracted")),
        "correct": bool(client_scoring.get("correct")),
        "finish_reason": _optional_string(response.get("finish_reason")),
        "latency_seconds": _number(timing.get("latency_seconds")),
        "started_at": _optional_string(timing.get("started_at")) or "",
        "finished_at": _optional_string(timing.get("finished_at")) or "",
        "attempts": _int(timing.get("attempts")),
        "usage": _usage(item.get("usage")),
        "error": _optional_string(response.get("error")),
    }


def _public_item(item: ScoredItem) -> JsonObject:
    result: JsonObject = {
        "id": item["id"],
        "bench": item["bench"],
        "extracted": item["extracted"],
        "correct": item["correct"],
        "finish_reason": item["finish_reason"],
        "error": item["error"],
    }
    if "failure_kind" in item:
        result["failure_kind"] = item["failure_kind"]
    return result


def _baselines(suite_items: Mapping[tuple[str, str], SuiteItem]) -> dict[str, float]:
    baselines: dict[str, float] = {}
    for suite_item in suite_items.values():
        baselines[suite_item.bench] = suite_item.baseline
    return baselines


def _wall_time(items: list[ScoredItem]) -> float:
    return sum(item["latency_seconds"] for item in items)


def _usage(value: JsonValue | None) -> Usage:
    data = _object(value)
    return {
        "prompt_tokens": _nullable_int(data.get("prompt_tokens")),
        "completion_tokens": _nullable_int(data.get("completion_tokens")),
        "total_tokens": _nullable_int(data.get("total_tokens")),
    }


def _object(value: JsonValue | None) -> JsonObject:
    return dict(value) if isinstance(value, dict) else {}


def _string_or_error(value: JsonValue | None, label: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise SubmissionValidationError(f"{label} must be a non-empty string")


def _optional_string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _number(value: JsonValue | None) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _int(value: JsonValue | None) -> int:
    if isinstance(value, bool):
        return 0
    return value if isinstance(value, int) else 1


def _nullable_int(value: JsonValue | None) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None

from __future__ import annotations

from typing import Final

from localbench._types import JsonObject, JsonValue

CLASS_EXACT: Final = "exact"
CLASS_BENIGN: Final = "benign"
CLASS_SCORE_CHANGING: Final = "score_changing"


def compare_client_divergence(items: list[JsonObject], recomputed: JsonObject) -> JsonObject:
    per_item = [
        _compare_item(item, recomputed_item)
        for item, recomputed_item in zip(items, _recomputed_items(recomputed), strict=True)
    ]
    items_changed = sum(1 for item in per_item if item["class"] != CLASS_EXACT)
    score_changing = [item for item in per_item if item["class"] == CLASS_SCORE_CHANGING]
    return {
        "items_compared": len(per_item),
        "items_changed": items_changed,
        "score_changing_count": len(score_changing),
        "classification": _overall_classification(items_changed, len(score_changing)),
        "rank_improving_tamper": _rank_improving_tamper(score_changing),
        "per_item": per_item,
    }


def _compare_item(item: JsonObject, recomputed_item: JsonObject) -> JsonObject:
    claimed = _scoring_claim(_object(item.get("client_scoring")))
    rescored = _scoring_claim(recomputed_item)
    return {
        "id": _string(recomputed_item.get("id")) or _string(item.get("item_id")) or "",
        "bench": _string(recomputed_item.get("bench")) or _string(item.get("bench")) or "",
        "claimed": claimed,
        "recomputed": rescored,
        "class": _item_class(claimed, rescored),
    }


def _item_class(claimed: JsonObject, recomputed: JsonObject) -> str:
    if claimed == recomputed:
        return CLASS_EXACT
    if claimed.get("correct") != recomputed.get("correct"):
        return CLASS_SCORE_CHANGING
    return CLASS_BENIGN


def _overall_classification(items_changed: int, score_changing_count: int) -> str:
    if score_changing_count > 0:
        return CLASS_SCORE_CHANGING
    if items_changed > 0:
        return CLASS_BENIGN
    return CLASS_EXACT


def _rank_improving_tamper(score_changing: list[JsonObject]) -> bool:
    # ANY score-changing item claimed correct where the authoritative recompute says wrong
    # (an inflation in the submitter's favour) flags tamper. `any` — NOT `all` — so an
    # attacker cannot mask a real inflation by pairing it with a throwaway under-claim.
    # Honest under-claimers (claimed wrong / recomputed right) are still never flagged:
    # `any([])` is False, and a not-in-favour change fails the predicate.
    return any(
        _object(item.get("claimed")).get("correct") is True
        and _object(item.get("recomputed")).get("correct") is False
        for item in score_changing
    )


def _scoring_claim(value: JsonObject) -> JsonObject:
    return {
        "correct": _bool_or_none(value.get("correct")),
        "extracted": _string(value.get("extracted")),
        "failure_kind": _string(value.get("failure_kind")),
    }


def _recomputed_items(recomputed: JsonObject) -> list[JsonObject]:
    value = recomputed.get("items")
    return [dict(item) for item in value] if isinstance(value, list) and all(isinstance(item, dict) for item in value) else []


def _object(value: JsonValue | None) -> JsonObject:
    return dict(value) if isinstance(value, dict) else {}


def _string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _bool_or_none(value: JsonValue | None) -> bool | None:
    return value if isinstance(value, bool) else None

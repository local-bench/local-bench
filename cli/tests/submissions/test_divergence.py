from __future__ import annotations

from localbench.submissions.divergence import compare_client_divergence


def _items(*claims: bool) -> list[dict]:
    return [
        {"item_id": chr(ord("a") + i), "bench": "mmlu_pro", "client_scoring": {"correct": c}}
        for i, c in enumerate(claims)
    ]


def _recomputed(*correct: bool) -> dict:
    return {"items": [{"id": chr(ord("a") + i), "bench": "mmlu_pro", "correct": c} for i, c in enumerate(correct)]}


def test_rank_improving_tamper_flags_mixed_bundle_with_one_inflation() -> None:
    # Regression guard: an attacker must NOT be able to mask a rank-improving inflation by
    # pairing it with a throwaway under-claim. ANY in-favour score change flags tamper.
    # item a: claimed correct, recomputed wrong  -> inflation (in favour)
    # item b: claimed wrong,   recomputed correct -> under-claim (NOT in favour)
    result = compare_client_divergence(_items(True, False), _recomputed(False, True))

    assert result["score_changing_count"] == 2
    assert result["rank_improving_tamper"] is True


def test_rank_improving_tamper_false_for_pure_under_claim() -> None:
    # Honest under-claimer (claimed wrong, recomputed right) is never flagged as tamper.
    result = compare_client_divergence(_items(False), _recomputed(True))

    assert result["score_changing_count"] == 1
    assert result["rank_improving_tamper"] is False


def test_rank_improving_tamper_false_for_clean_bundle() -> None:
    result = compare_client_divergence(_items(True, False), _recomputed(True, False))

    assert result["score_changing_count"] == 0
    assert result["classification"] == "exact"
    assert result["rank_improving_tamper"] is False

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import TypeAlias

import pytest

from suite import build_v1_mmlu_pro as builder

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def test_candidate_from_row_trims_na_fillers_and_remaps_answer() -> None:
    # Given an MMLU-Pro row where "N/A" pads the original options before the keyed answer.
    row = _row(
        question_id=101,
        options=["alpha", "N/A", "bravo", "N/A"],
        answer="C",
        category="physics",
    )

    # When converting the source row into a local-bench candidate.
    candidate, drop_reason = builder._candidate_from_row(row)

    # Then filler options are removed and the gold letter is remapped onto the real options.
    assert drop_reason is None
    assert candidate is not None
    assert candidate.options == ("alpha", "bravo")
    assert candidate.answer == "B"
    assert candidate.category == "physics"


@pytest.mark.parametrize(
    ("question_id", "options", "answer", "reason"),
    [
        (201, ["alpha", "N/A"], "B", "gold_is_na"),
        (202, ["alpha", "bravo"], "C", "missing_or_ambiguous_gold"),
        (203, ["alpha", "alpha", "N/A"], "A", "ambiguous_duplicate_options"),
    ],
)
def test_candidate_from_row_rejects_unscorable_keys_and_options(
    question_id: int,
    options: list[str],
    answer: str,
    reason: str,
) -> None:
    # Given source rows with invalid keyed answers or ambiguous real options.
    row = _row(question_id=question_id, options=options, answer=answer)

    # When converting each row.
    candidate, drop_reason = builder._candidate_from_row(row)

    # Then the row is dropped with a stable reason for the datasheet.
    assert candidate is None
    assert drop_reason == reason


def test_stratified_sample_is_stable_for_fixed_seed_on_tiny_fixture() -> None:
    # Given a small in-memory fixture spanning two categories.
    candidates = [
        _candidate(question_id=1, category="history"),
        _candidate(question_id=2, category="history"),
        _candidate(question_id=3, category="history"),
        _candidate(question_id=4, category="math"),
        _candidate(question_id=5, category="math"),
        _candidate(question_id=6, category="math"),
    ]

    # When sampling the same rows in different input orders with a fixed seed.
    first = builder._stratified_sample(candidates, target_count=4, sample_seed="fixed")
    second = builder._stratified_sample(list(reversed(candidates)), target_count=4, sample_seed="fixed")

    # Then selection and output ordering are deterministic, with proportional category coverage.
    assert [candidate.question_id for candidate in first] == [
        candidate.question_id for candidate in second
    ]
    assert Counter(candidate.category for candidate in first) == {"history": 2, "math": 2}


def test_chance_baseline_is_mean_inverse_real_option_count() -> None:
    # Given emitted candidates with variable real option counts.
    candidates = [
        _candidate(question_id=1, options=("a", "b")),
        _candidate(question_id=2, options=("a", "b", "c", "d")),
        _candidate(question_id=3, options=("a", "b", "c", "d", "e")),
    ]

    # When computing the suite chance baseline.
    baseline = builder._chance_baseline(candidates)

    # Then it is the selected-set mean of per-item random-choice chance.
    assert baseline == pytest.approx(((1 / 2) + (1 / 4) + (1 / 5)) / 3)


def _row(
    *,
    question_id: int,
    options: list[str],
    answer: str,
    category: str = "biology",
) -> JsonObject:
    return {
        "question_id": question_id,
        "question": f"Question {question_id}?",
        "options": options,
        "answer": answer,
        "answer_index": builder.LETTERS.index(answer) if answer in builder.LETTERS else -1,
        "cot_content": "",
        "category": category,
        "src": "unit-test",
    }


def _candidate(
    *,
    question_id: int,
    category: str = "biology",
    options: Iterable[str] = ("a", "b", "c"),
) -> builder.Candidate:
    return builder.Candidate(
        question_id=question_id,
        question=f"Question {question_id}?",
        options=tuple(options),
        answer="A",
        category=category,
    )

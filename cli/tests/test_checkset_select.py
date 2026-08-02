from __future__ import annotations

from inspect import signature
from pathlib import Path

import pytest

from localbench.checkset.input_runs import load_verified_runs, read_json, read_jsonl
from localbench.checkset.models import ChecksetBuildError
from localbench.checkset.select import (
    SourceItem,
    select_cost_aware,
    select_ifbench,
    select_math_aime,
)
from localbench.checkset.sources import IFBENCH_QUOTAS, _source_items


def _source_item(
    item_id: str,
    *,
    informative: bool = False,
    latency: float = 1.0,
    instruction_ids: tuple[str, ...] = (),
) -> SourceItem:
    return SourceItem(
        item_id=item_id,
        content_sha256="a" * 64,
        informative=informative,
        latency_seconds=latency,
        instruction_ids=instruction_ids,
        tool_count=1,
    )


def test_cost_aware_selection_prefers_below_pool_median_then_id() -> None:
    # Given a pool whose ID order disagrees with its latency tier.
    items = (
        _source_item("item-001", latency=10.0),
        _source_item("item-002", latency=1.0),
        _source_item("item-003", latency=2.0),
        _source_item("item-004", latency=20.0),
    )

    # When a two-item cost-aware draw is made.
    selected = select_cost_aware(items, quota=2)

    # Then both below-median items are chosen in ascending ID order.
    assert tuple(item.item_id for item in selected) == ("item-002", "item-003")


def test_cost_aware_selection_uses_explicit_full_pool_median() -> None:
    # Given complement candidates whose own median differs from the full-pool median.
    candidates = (
        _source_item("item-001", latency=4.0),
        _source_item("item-002", latency=3.0),
    )
    full_pool = (
        _source_item("pool-001", latency=1.0),
        _source_item("pool-002", latency=2.0),
        *candidates,
    )

    # When selection is ranked against the full pool.
    selected = select_cost_aware(candidates, quota=1, median_pool=full_pool)

    # Then both candidates are above-median and ascending ID breaks the tie.
    assert selected[0].item_id == "item-001"


def test_ifbench_selection_uses_frozen_primary_stratum_and_informative_priority() -> None:
    # Given rows where list order differs from canonical instruction-ID order.
    items = (
        _source_item(
            "ifbench-001",
            informative=True,
            instruction_ids=("words:vowel", "format:list"),
        ),
        _source_item("ifbench-002", instruction_ids=("format:quotes",)),
        _source_item("ifbench-003", instruction_ids=("words:alphabet",)),
    )

    # When quotas are allocated for the two represented rollups.
    selected = select_ifbench(items, {"format": 2, "words": 1})

    # Then the first row belongs to format and informative rows rank first.
    assert tuple(item.item_id for item in selected) == (
        "ifbench-001",
        "ifbench-002",
        "ifbench-003",
    )


def test_ifbench_selector_cannot_accept_an_outcome_quota() -> None:
    # Given the frozen selector API.
    parameters = signature(select_ifbench).parameters

    # When its selection inputs are inspected, then no outcome quota is accepted.
    assert "informative_quota" not in parameters


def test_real_ifbench_selection_emerges_as_72_informative_and_48_complement() -> None:
    # Given the T1-pinned IFBench suite and four verified run bundles.
    repo_root = Path(__file__).resolve().parents[2]
    manifest = read_json(repo_root / "docs" / "v2" / "inputs" / "inputs-manifest.json")
    correctness, latency = load_verified_runs(manifest, suite_root=repo_root / "suite" / "v2")
    rows = read_jsonl(repo_root / "suite" / "v2" / "ifbench.jsonl")
    source_items = _source_items("ifbench", rows, correctness, latency)

    # When selection uses only the frozen primary-stratum mechanics.
    selected = select_ifbench(source_items, IFBENCH_QUOTAS)

    # Then the locked outcome emerges without an outcome quota in the selector API.
    assert sum(item.informative for item in selected) == 72
    assert sum(not item.informative for item in selected) == 48


def test_math_medium_draw_is_deterministic_and_subject_stratified() -> None:
    # Given three upstream subjects with stable upstream indices.
    rows = tuple(
        {"problem": f"p{index}", "answer": str(index), "subject": subject}
        for index, subject in enumerate(("a", "b", "c") * 4)
    )

    # When the rows-only pure selector is called twice.
    first = select_math_aime(rows, quota=6, seed=20260802)
    second = select_math_aime(rows, quota=6, seed=20260802)

    # Then it returns the same two upstream indices per topic.
    assert first == second
    assert {subject: sum(row.subject == subject for row in first) for subject in ("a", "b", "c")} == {
        "a": 2,
        "b": 2,
        "c": 2,
    }


def test_math_medium_draw_rejects_empty_input_with_typed_error() -> None:
    # Given an empty pinned en-easy split, when selection is attempted, then the build fails explicitly.
    with pytest.raises(ChecksetBuildError, match="OlymMATH en-easy input is empty"):
        select_math_aime((), quota=30, seed=20260802)

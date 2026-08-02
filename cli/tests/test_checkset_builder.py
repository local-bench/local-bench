from __future__ import annotations

import json
from pathlib import Path

import pytest
from localbench.checkset.build import build_t2_scaffold, emit_manifest
from localbench.checkset.models import ItemRecord, ModuleRecord
from localbench.checkset.select import (
    SourceItem,
    select_cost_aware,
    select_ifbench,
    select_math_medium,
)
from localbench.checkset.sources import build_local_modules
from localbench.checkset.upstream import prepare_gpqa
from localbench.cli import main


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


def test_math_medium_draw_is_deterministic_and_topic_stratified() -> None:
    # Given three upstream topics with stable upstream indices.
    rows = tuple(
        {"problem": f"p{index}", "answer": str(index), "topic": topic}
        for index, topic in enumerate(("a", "b", "c") * 4)
    )

    # When the rows-only pure selector is called twice.
    first = select_math_medium(rows, quota=6, seed=20260802)
    second = select_math_medium(rows, quota=6, seed=20260802)

    # Then it returns the same two upstream indices per topic.
    assert first == second
    assert {topic: sum(row.topic == topic for row in first) for topic in ("a", "b", "c")} == {
        "a": 2,
        "b": 2,
        "c": 2,
    }


def test_scaffold_records_t3_dependency_without_claiming_authored_totals(tmp_path: Path) -> None:
    # Given no T3 authored-content file.
    output = tmp_path / "check-set-v1.t2-draft.json"

    # When the T2 scaffold is built from a minimal injected selection set.
    result = build_t2_scaffold(
        output,
        modules=(ModuleRecord(name="coding", scored=1, items=(ItemRecord("x", "b" * 64),)),),
        knowledge_status="pending_fetch",
        knowledge_error="gated",
    )

    # Then the artifact is explicitly incomplete and byte-stable on a second write.
    first_bytes = output.read_bytes()
    build_t2_scaffold(
        output,
        modules=(ModuleRecord(name="coding", scored=1, items=(ItemRecord("x", "b" * 64),)),),
        knowledge_status="pending_fetch",
        knowledge_error="gated",
    )
    assert output.read_bytes() == first_bytes
    assert result["draft"] is True
    assert result["status"] == "pending_dependencies"
    assert result["pending_dependencies"] == ["tools-stateful", "sanity-gates"]


def test_final_emit_rejects_non_locked_authored_totals(tmp_path: Path) -> None:
    # Given an incomplete module list.
    modules = (ModuleRecord(name="knowledge", scored=198, items=()),)

    # When final manifest emission is attempted, then it fails loudly.
    with pytest.raises(ValueError, match=r"576 scored \+ 18 gates \+ 6 spares = 600"):
        emit_manifest(tmp_path / "manifest.json", modules=modules, stateful={})


def test_final_emit_writes_canonical_sidecar_and_is_byte_identical(tmp_path: Path) -> None:
    # Given locked module counts and T3 stateful metadata.
    counts = {
        "knowledge": 198,
        "coding": 96,
        "instruction": 120,
        "math": 60,
        "tools-single": 54,
        "tools-stateful": 48,
        "sanity-gates": 18,
    }
    modules = tuple(ModuleRecord(name=name, scored=count, items=()) for name, count in counts.items())
    stateful = {"templates": [f"t{i}" for i in range(12)], "instances": [], "spares_ordered": list(range(6)), "cluster_map": {}}
    output = tmp_path / "manifest.json"

    # When the final draft is emitted twice.
    emit_manifest(output, modules=modules, stateful=stateful)
    first_bytes = output.read_bytes()
    emit_manifest(output, modules=modules, stateful=stateful)

    # Then canonical bytes and their sha256 sidecar are stable.
    assert output.read_bytes() == first_bytes
    assert json.loads(output.read_text(encoding="utf-8"))["draft"] is True
    assert (tmp_path / "manifest.json.sha256").read_text(encoding="ascii").endswith("  manifest.json\n")


def test_real_pinned_inputs_produce_locked_t2_local_selections() -> None:
    # Given the T1-pinned suite and four verified run bundles.
    repo_root = Path(__file__).resolve().parents[2]

    # When the local-only T2 selectors run.
    modules, exclusions = build_local_modules(repo_root)

    # Then all pre-upstream module counts and frozen informative splits match the lock.
    by_name = {module.name: module for module in modules}
    assert len(by_name["coding"].items) == 96
    assert len(by_name["instruction"].items) == 120
    assert len(by_name["math-legacy"].items) == 30
    assert len(by_name["tools-single"].items) == 54
    assert len(exclusions) == 7


def test_gpqa_preparation_strips_canary_and_shuffles_deterministically() -> None:
    # Given a GPQA-shaped row containing a canary and one correct answer.
    row = {
        "Record ID": "rec-1",
        "Question": "question",
        "Correct Answer": "correct",
        "Incorrect Answer 1": "wrong-1",
        "Incorrect Answer 2": "wrong-2",
        "Incorrect Answer 3": "wrong-3",
        "Canary String": "do-not-include",
    }

    # When the same revision-pinned row is prepared twice.
    first, first_log = prepare_gpqa((row,), revision="f" * 40)
    second, second_log = prepare_gpqa((row,), revision="f" * 40)

    # Then only content hashes and canary-removal evidence remain and are stable.
    assert first == second
    assert first_log == second_log
    assert first.scored == 1
    assert first.items[0].item_id == "gpqa-diamond-rec-1"
    assert first_log[0]["field"] == "Canary String"
    assert "do-not-include" not in json.dumps(first.as_json())


def test_checkset_build_cli_emits_an_explicit_offline_scaffold(tmp_path: Path) -> None:
    # Given the internal CLI in offline upstream mode.
    repo_root = Path(__file__).resolve().parents[2]
    output = tmp_path / "t2-draft.json"

    # When the check-set scaffold command runs.
    exit_code = main(
        (
            "checkset",
            "build",
            "--repo-root",
            str(repo_root),
            "--output",
            str(output),
            "--offline-upstream",
        )
    )

    # Then it emits a deterministic pending artifact without claiming completion.
    document = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert document["status"] == "pending_dependencies"
    assert document["pending_dependencies"] == ["knowledge", "math-medium", "tools-stateful", "sanity-gates"]

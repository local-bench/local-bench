from __future__ import annotations

import json
from pathlib import Path

import pytest

import localbench.checkset.command as checkset_command
from localbench.checkset.models import ItemRecord, ModuleRecord
from localbench.checkset.select import AimeMathItem, select_math_aime
from localbench.checkset.upstream import combine_math_module, prepare_gpqa
from localbench.cli import main


def test_math_aime_draw_combines_with_legacy_math() -> None:
    # Given 30 legacy records and 30 deterministic en-easy selections.
    legacy = ModuleRecord(
        name="math-legacy",
        scored=30,
        items=tuple(ItemRecord(f"legacy-{index:02d}", f"{index:064x}") for index in range(30)),
    )
    rows = tuple(
        {"problem": f"problem-{index}", "answer": str(index), "subject": f"subject-{index % 3}"}
        for index in range(30)
    )
    selected = select_math_aime(rows, quota=30)

    # When the selected AIME-band records are combined with legacy math.
    combined = combine_math_module(legacy, selected)

    # Then the published math module contains both frozen halves and stable AIME ids.
    assert combined.name == "math"
    assert combined.scored == 60
    assert combined.items[:30] == legacy.items
    assert tuple(item.item_id for item in combined.items[30:]) == tuple(
        f"olymmath-en-easy-{index:05d}" for index in range(30)
    )


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
    assert first.items[0].content_sha256 == "8723c9c22a3ee36f5abf8b151c0aacace40fbc8229636fd2c31cac9970d67249"
    assert first_log[0]["field"] == "Canary String"
    assert first_log[0]["removed_sha256"] == "8c85645bf53ded804cea06c3fe2006c6be6535c07339e1161acb46f9b38fa4f8"
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
    assert document["pending_dependencies"] == ["knowledge", "math-aime", "tools-stateful", "sanity-gates"]


def test_online_build_carries_provenance_and_combined_math(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given successful pinned GPQA and OlymMATH acquisitions.
    repo_root = Path(__file__).resolve().parents[2]
    knowledge = ModuleRecord(
        name="knowledge",
        scored=198,
        items=tuple(ItemRecord(f"gpqa-{index:03d}", f"{index:064x}") for index in range(198)),
    )
    canary_log = tuple(
        {"field": "Canary String", "item_id": item.item_id, "removed_sha256": "a" * 64}
        for item in knowledge.items
    )
    aime = tuple(AimeMathItem(index, f"subject-{index % 3}", f"{index + 1000:064x}") for index in range(30))
    monkeypatch.setattr(checkset_command, "fetch_gpqa", lambda: (knowledge, canary_log))
    monkeypatch.setattr(checkset_command, "fetch_math_aime", lambda: aime)

    # When the online T2 builder runs.
    output = tmp_path / "t2-draft.json"
    exit_code, _ = checkset_command.build_command(repo_root, output, offline_upstream=False)

    # Then provenance, the complete canary log, and both math halves reach the scaffold.
    document = json.loads(output.read_text(encoding="utf-8"))
    modules = {module["name"]: module for module in document["modules"]}
    assert exit_code == 2
    assert document["pending_dependencies"] == ["tools-stateful", "sanity-gates"]
    assert len(document["source_metadata"]["gpqa_canary_strip_log"]) == 198
    assert document["source_metadata"]["math_aime"]["config"] == "en-easy"
    assert modules["math"]["scored"] == 60
    assert len(modules["math"]["items"]) == 60
